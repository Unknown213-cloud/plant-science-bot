#!/usr/bin/env python3
"""
Plant Science Bot - Automated Instagram Publisher
=================================================
Publishes educational infographics and multi-slide carousel posts to Instagram
via the Instagram Graph API (with Instagram Login), using images hosted on GitHub
(raw.githubusercontent.com), and archives published posts to posted/.

Supports:
    1. Multi-slide Carousel posts (folder in queue/ with slide_*.png and caption.txt)
    2. Single-image posts (standalone image in queue/ or 1-image folder)

Requirements:
    - Environment variables:
        IG_ACCESS_TOKEN: Long-lived Instagram User Access Token
        IG_USER_ID: Instagram Business or Creator User ID
    - Optional:
        GITHUB_REPOSITORY: 'owner/repo' (defaults to git config or Unknown213-cloud/plant-science-bot)
        GITHUB_REF_NAME: branch name (defaults to 'main')

Meta Instagram Graph API Limits:
    - Carousel items: Minimum 2, Maximum 10 items.
    - Publishing rate limit: 25 published posts per 24 hours per account.
    - Media containers expire 24 hours after creation if unpublished.
    - All carousel images must share the same aspect ratio (4:5, 1080x1350 recommended).
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
from publication import validate_post, verify_public_images, publish_once, read_json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Ensure utf-8 output encoding across Windows shells and CI environments
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import requests
except ImportError:
    print("Error: 'requests' library is required. Install it using 'pip install requests'.", file=sys.stderr)
    sys.exit(1)

SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
DEFAULT_REPO = "Unknown213-cloud/plant-science-bot"
DEFAULT_BRANCH = "main"
GRAPH_API_BASE = "https://graph.instagram.com"

# Meta API Constraints
CAROUSEL_MIN_ITEMS = 2
CAROUSEL_MAX_ITEMS = 10
API_DAILY_POST_LIMIT = 25


@dataclass
class QueuedPost:
    post_type: str  # 'carousel' or 'single'
    path: Path  # directory or file
    mtime: float
    name: str
    slides: List[Path] = field(default_factory=list)
    caption: str = ""


def get_git_repo_info() -> Tuple[str, str]:
    """
    Detect the GitHub repository ('owner/repo') and current branch name.
    Prioritizes GitHub Actions environment variables, then falls back
    to local git commands, and finally defaults.
    """
    repo = os.getenv("GITHUB_REPOSITORY")
    branch = os.getenv("GITHUB_REF_NAME")

    if not repo:
        try:
            url_proc = subprocess.run(
                ["git", "config", "--get", "remote.origin.url"],
                capture_output=True,
                text=True,
                check=False,
                cwd=Path(__file__).resolve().parent,
            )
            raw_url = url_proc.stdout.strip()
            if raw_url:
                if raw_url.startswith("git@github.com:"):
                    repo = raw_url.split("git@github.com:")[1].removesuffix(".git")
                elif "github.com/" in raw_url:
                    repo = raw_url.split("github.com/")[1].removesuffix(".git")
        except Exception:
            pass

    if not branch:
        try:
            branch_proc = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                check=False,
                cwd=Path(__file__).resolve().parent,
            )
            detected_branch = branch_proc.stdout.strip()
            if detected_branch and detected_branch != "HEAD":
                branch = detected_branch
        except Exception:
            pass

    return (repo or DEFAULT_REPO, branch or DEFAULT_BRANCH)


def load_captions(captions_path: Path) -> Dict[str, str]:
    """Load captions mapping from a JSON file."""
    if not captions_path.exists():
        return {}
    try:
        with open(captions_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            parsed = {}
            for k, v in data.items():
                if isinstance(v, str):
                    parsed[k] = v
                elif isinstance(v, dict):
                    parsed[k] = v.get("caption") or v.get("text") or ""
                else:
                    parsed[k] = str(v)
            return parsed
    except Exception as e:
        print(f"Warning: Failed to parse captions at {captions_path}: {e}", file=sys.stderr)
        return {}


def save_captions(captions_path: Path, data: dict) -> None:
    """Save dictionary to captions.json with formatting."""
    captions_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = captions_path.with_suffix(".tmp")
    with open(temporary, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    temporary.replace(captions_path)


def build_raw_github_url(repo: str, branch: str, file_rel_path: str) -> str:
    """Build the public raw.githubusercontent.com URL for a repository asset."""
    normalized_path = file_rel_path.replace("\\", "/").lstrip("/")
    parts = [urllib.parse.quote(part, safe="") for part in normalized_path.split("/")]
    return f"https://raw.githubusercontent.com/{repo}/{urllib.parse.quote(branch, safe='')}/{'/'.join(parts)}"


def find_queued_posts(queue_dir: Path) -> List[QueuedPost]:
    """
    Scan queue/ for both carousel folders and standalone single images.
    Returns all candidates with their slides, captions, and modification times.
    """
    if not queue_dir.exists() or not queue_dir.is_dir():
        return []

    candidates: List[QueuedPost] = []
    root_captions = load_captions(queue_dir / "captions.json")

    for entry in queue_dir.iterdir():
        # Case A: Post is a Subdirectory (Carousel or Folder Post)
        if entry.is_dir():
            slides = [
                f for f in entry.iterdir()
                if f.is_file() and f.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
            ]
            if not slides:
                continue

            # Sort slides naturally (e.g. slide_01.png, slide_02.png)
            import re
            slides.sort(key=lambda s: [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", s.name)])

            # Caption resolution: caption.txt preferred, then captions.json
            caption = ""
            caption_file = entry / "caption.txt"
            if caption_file.exists():
                try:
                    caption = caption_file.read_text(encoding="utf-8").strip()
                except Exception as e:
                    print(f"Warning: Could not read {caption_file}: {e}", file=sys.stderr)

            if not caption:
                dir_captions = load_captions(entry / "captions.json")
                caption = dir_captions.get(slides[0].name, "") or dir_captions.get("caption", "")

            post_type = "carousel" if len(slides) >= 2 else "single"
            candidates.append(
                QueuedPost(
                    post_type=post_type,
                    path=entry,
                    mtime=entry.stat().st_mtime,
                    name=entry.name,
                    slides=slides,
                    caption=caption,
                )
            )

        # Case B: Standalone Image File in queue/ (Legacy single-image post)
        elif entry.is_file() and entry.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
            caption = root_captions.get(entry.name, "").strip()
            # Also check if a matching entry.txt file exists
            txt_match = entry.with_suffix(".txt")
            if not caption and txt_match.exists():
                try:
                    caption = txt_match.read_text(encoding="utf-8").strip()
                except Exception:
                    pass

            candidates.append(
                QueuedPost(
                    post_type="single",
                    path=entry,
                    mtime=entry.stat().st_mtime,
                    name=entry.name,
                    slides=[entry],
                    caption=caption,
                )
            )

    # Sort by numeric prefix if present (e.g. 01-leaf-layers), otherwise by mtime
    def sort_key(c: QueuedPost):
        import re
        m = re.match(r"^(\d+)", c.name)
        if m:
            return (0, int(m.group(1)), c.name.lower())
        return (1, c.mtime, c.name.lower())

    candidates.sort(key=sort_key)
    return candidates


def refresh_access_token(access_token: str, env_file_path: Optional[Path] = None) -> Optional[dict]:
    """
    Refresh a long-lived Instagram user access token.
    Handles Meta's 24-hour rate limit gracefully.
    """
    print("[Token] Refreshing Instagram User Access Token...")
    url = f"{GRAPH_API_BASE}/refresh_access_token"
    params = {
        "grant_type": "ig_refresh_token",
        "access_token": access_token,
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        res_data = response.json()

        if response.status_code != 200 or "access_token" not in res_data:
            err_msg = ""
            if isinstance(res_data, dict):
                err_msg = res_data.get("error", {}).get("message", "")
            if "24 hours" in err_msg.lower() or "cannot be refreshed" in err_msg.lower():
                print("[Token Info] Token is active and was generated/refreshed within the last 24 hours (refresh only allowed every 24h+).")
            else:
                print(f"[Token Notice] Refresh returned HTTP {response.status_code}. Continuing with current token.", file=sys.stderr)
            return None

        new_token = res_data["access_token"]
        expires_in = res_data.get("expires_in", 0)
        days_left = expires_in // 86400

        print(f"[Token Success] Token successfully refreshed! Valid for ~{days_left} days ({expires_in}s).")

        if env_file_path and env_file_path.exists():
            try:
                content = env_file_path.read_text(encoding="utf-8")
                lines = content.splitlines()
                updated = False
                new_lines = []
                for line in lines:
                    if line.startswith("IG_ACCESS_TOKEN="):
                        new_lines.append(f"IG_ACCESS_TOKEN={new_token}")
                        updated = True
                    else:
                        new_lines.append(line)
                if not updated:
                    new_lines.append(f"IG_ACCESS_TOKEN={new_token}")
                env_file_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
                print(f"[Token] Updated {env_file_path.name} with refreshed token.")
            except Exception as e:
                print(f"[Token] Notice: Could not update local .env file: {e}")

        return res_data
    except Exception as e:
        print(f"[Token Warning] Token refresh unavailable ({type(e).__name__}); using current token.", file=sys.stderr)
        return None


def poll_media_container_status(creation_id: str, access_token: str, max_wait_sec: int = 60) -> bool:
    """Poll status of an Instagram media container until FINISHED or error."""
    url = f"{GRAPH_API_BASE}/{creation_id}"
    params = {"fields": "status_code,status", "access_token": access_token}

    start_time = time.time()
    while time.time() - start_time < max_wait_sec:
        try:
            res = requests.get(url, params=params, timeout=15)
            if res.status_code == 200:
                data = res.json()
                status_code = data.get("status_code")
                if status_code == "FINISHED":
                    return True
                elif status_code in {"ERROR", "EXPIRED"}:
                    print(f"[API Error] Media container error: {data}", file=sys.stderr)
                    return False
                elif status_code == "IN_PROGRESS":
                    time.sleep(3)
                    continue
                elif status_code == "PUBLISHED":
                    return False
        except Exception as e:
            print(f"[API Warning] Container status check warning: {e}")

        time.sleep(3)

    print("[API Error] Container did not become FINISHED before timeout.", file=sys.stderr)
    return False


def post_single_image(
    image_url: str,
    caption: str,
    access_token: str,
    user_id: Optional[str] = None,
    before_publish=None,
) -> str:
    """Publish a single image to Instagram via Instagram Graph API."""
    actor = user_id or "me"
    container_endpoint = f"{GRAPH_API_BASE}/{actor}/media"
    publish_endpoint = f"{GRAPH_API_BASE}/{actor}/media_publish"

    print(f"[API] Creating single image container at {container_endpoint}...")
    container_payload = {
        "image_url": image_url,
        "caption": caption,
        "access_token": access_token,
    }

    resp = requests.post(container_endpoint, data=container_payload, timeout=30)
    data = resp.json()

    if resp.status_code != 200 and user_id and ("user" in str(data).lower() or "id" in str(data).lower()):
        print(f"[API Notice] Retrying container creation with /{user_id}/media...")
        container_endpoint = f"{GRAPH_API_BASE}/{user_id}/media"
        publish_endpoint = f"{GRAPH_API_BASE}/{user_id}/media_publish"
        resp = requests.post(container_endpoint, data=container_payload, timeout=30)
        data = resp.json()

    if resp.status_code != 200 or "id" not in data:
        raise RuntimeError(f"Instagram Container Creation failed [{resp.status_code}]: {data}")

    creation_id = data["id"]
    print(f"[API Success] Container created with ID: {creation_id}")

    if not poll_media_container_status(creation_id, access_token):
        raise RuntimeError("Single image container is not ready; publication stopped")
    if before_publish:
        before_publish(creation_id)

    print(f"[API] Publishing container at {publish_endpoint}...")
    pub_payload = {"creation_id": creation_id, "access_token": access_token}
    pub_resp = requests.post(publish_endpoint, data=pub_payload, timeout=30)
    pub_data = pub_resp.json()

    if pub_resp.status_code != 200 or "id" not in pub_data:
        raise RuntimeError(f"Instagram Media Publish failed [{pub_resp.status_code}]: {pub_data}")

    media_id = pub_data["id"]
    print(f"[API Success] Published successfully! Media ID: {media_id}")
    return media_id


def post_carousel(
    slide_urls: List[str],
    caption: str,
    access_token: str,
    user_id: Optional[str] = None,
    before_publish=None,
) -> str:
    """
    Publish a multi-slide Carousel to Instagram via Instagram Graph API:
      1. For each slide: POST /me/media with is_carousel_item=true
      2. Wait until all child containers are FINISHED
      3. Create parent container: POST /me/media with media_type=CAROUSEL, children=id1,id2,...
      4. Wait until parent container is FINISHED
      5. Publish: POST /me/media_publish with creation_id=parent_id
    """
    if len(slide_urls) < CAROUSEL_MIN_ITEMS:
        raise ValueError(f"Carousel requires at least {CAROUSEL_MIN_ITEMS} slides, found {len(slide_urls)}.")

    if len(slide_urls) > CAROUSEL_MAX_ITEMS:
        raise ValueError(f"Carousel exceeds {CAROUSEL_MAX_ITEMS} slides; refusing to truncate")

    actor = user_id or "me"
    container_endpoint = f"{GRAPH_API_BASE}/{actor}/media"
    publish_endpoint = f"{GRAPH_API_BASE}/{actor}/media_publish"

    # Step 1: Create individual item containers
    child_ids: List[str] = []
    print(f"\n[API Carousel] Creating {len(slide_urls)} individual slide containers...")

    for idx, slide_url in enumerate(slide_urls, 1):
        print(f"  • Slide {idx}/{len(slide_urls)}: Creating container for {slide_url}...")
        payload = {
            "image_url": slide_url,
            "is_carousel_item": "true",
            "access_token": access_token,
        }

        resp = requests.post(container_endpoint, data=payload, timeout=30)
        data = resp.json()

        if resp.status_code != 200 and user_id and ("user" in str(data).lower() or "id" in str(data).lower()):
            container_endpoint = f"{GRAPH_API_BASE}/{user_id}/media"
            publish_endpoint = f"{GRAPH_API_BASE}/{user_id}/media_publish"
            resp = requests.post(container_endpoint, data=payload, timeout=30)
            data = resp.json()

        if resp.status_code != 200 or "id" not in data:
            raise RuntimeError(
                f"Failed to create carousel item {idx}/{len(slide_urls)} [{resp.status_code}]: {data}\n"
                f"URL tested: {slide_url}"
            )

        child_id = data["id"]
        print(f"    Container created: {child_id}. Waiting for ready status...")
        if not poll_media_container_status(child_id, access_token):
            raise RuntimeError(f"Carousel child {idx} is not ready; publication stopped")
        child_ids.append(child_id)

    # Step 2: Create parent carousel container
    print(f"\n[API Carousel] Creating parent carousel container with children: {','.join(child_ids)}...")
    parent_payload = {
        "media_type": "CAROUSEL",
        "children": ",".join(child_ids),
        "caption": caption,
        "access_token": access_token,
    }

    p_resp = requests.post(container_endpoint, data=parent_payload, timeout=30)
    p_data = p_resp.json()

    if p_resp.status_code != 200 or "id" not in p_data:
        raise RuntimeError(f"Instagram Parent Carousel Container Creation failed [{p_resp.status_code}]: {p_data}")

    carousel_container_id = p_data["id"]
    print(f"[API Success] Parent Carousel Container created: {carousel_container_id}")

    if not poll_media_container_status(carousel_container_id, access_token):
        raise RuntimeError("Parent carousel is not ready; publication stopped")
    if before_publish:
        before_publish(carousel_container_id)

    # Step 3: Publish Carousel
    print(f"[API Carousel] Publishing carousel container at {publish_endpoint}...")
    pub_payload = {
        "creation_id": carousel_container_id,
        "access_token": access_token,
    }

    pub_resp = requests.post(publish_endpoint, data=pub_payload, timeout=30)
    pub_data = pub_resp.json()

    if pub_resp.status_code != 200 or "id" not in pub_data:
        raise RuntimeError(f"Instagram Carousel Publish failed [{pub_resp.status_code}]: {pub_data}")

    media_id = pub_data["id"]
    print(f"\n🎉 [API Success] Carousel published successfully! Instagram Media ID: {media_id}")
    return media_id


def move_post_to_posted(
    post: QueuedPost,
    queue_dir: Path,
    posted_dir: Path,
    media_id: Optional[str] = None,
) -> None:
    """Move the published post (folder or file) to posted/ and record archive metadata."""
    posted_dir.mkdir(parents=True, exist_ok=True)
    destination = posted_dir / post.path.name

    if destination.exists():
        raise RuntimeError(f"Archive already exists: {destination}. Refusing to overwrite it.")

    # Update posted/captions.json
    posted_captions_file = posted_dir / "captions.json"
    posted_data = {}
    if posted_captions_file.exists():
        try:
            with open(posted_captions_file, "r", encoding="utf-8") as f:
                posted_data = json.load(f)
        except Exception as exc:
            raise RuntimeError("Archive history is unreadable; restore it before continuing") from exc

    was_standalone = post.path.is_file()
    posted_data[post.name] = {
        "caption": post.caption,
        "type": post.post_type,
        "slides": [s.name for s in post.slides],
        "slide_count": len(post.slides),
        "posted_at": datetime.now(timezone.utc).isoformat(),
        "media_id": media_id or "dry-run",
    }
    print(f"[Storage] Archiving {post.path} -> {destination}...")
    shutil.move(str(post.path), str(destination))
    save_captions(posted_captions_file, posted_data)
    print(f"[Storage] Recorded '{post.name}' in {posted_captions_file.name}.")

    # If it was a standalone image, clean up queue/captions.json
    if was_standalone:
        q_captions_file = queue_dir / "captions.json"
        if q_captions_file.exists():
            q_data = load_captions(q_captions_file)
            if post.name in q_data:
                del q_data[post.name]
                save_captions(q_captions_file, q_data)


def main():
    parser = argparse.ArgumentParser(
        description="Plant Science Bot: Publish queued botanical infographics and carousels to Instagram."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the posting workflow without making API calls or moving files.",
    )
    parser.add_argument(
        "--refresh-token",
        action="store_true",
        help="Refresh the long-lived Instagram User Access Token and exit.",
    )
    parser.add_argument(
        "--queue-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "queue",
        help="Directory containing queued posts (default: queue).",
    )
    parser.add_argument(
        "--posted-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "posted",
        help="Directory where posted posts are archived (default: posted).",
    )
    parser.add_argument(
        "--post",
        type=str,
        default=None,
        help="Select a specific post folder or file name in queue/ (default: oldest post).",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=None,
        help="GitHub repo in 'owner/repo' format (default: auto-detected).",
    )
    parser.add_argument(
        "--branch",
        type=str,
        default=None,
        help="GitHub branch name for raw URLs (default: main).",
    )

    parser.add_argument("--validate-all", action="store_true", help="Validate every queued image and caption locally, then exit.")
    parser.add_argument("--verify-hosted", action="store_true", help="Also check anonymous hosted image bytes during a dry run.")
    parser.add_argument("--skip-token-refresh", action="store_true", help="Use the token already refreshed by the workflow.")
    args = parser.parse_args()

    access_token = os.getenv("IG_ACCESS_TOKEN", "").strip()
    user_id = os.getenv("IG_USER_ID", "").strip()

    if args.refresh_token:
        if not access_token:
            print("Error: IG_ACCESS_TOKEN environment variable is required to refresh token.", file=sys.stderr)
            sys.exit(1)
        res = refresh_access_token(access_token, env_file_path=Path(".env"))
        sys.exit(0 if res else 1)

    detected_repo, detected_branch = get_git_repo_info()
    repo = args.repo or detected_repo
    branch = args.branch or detected_branch

    queue_dir = args.queue_dir
    posted_dir = args.posted_dir

    print("=" * 70)
    print("🌿 Plant Science Bot - Carousel & Infographic Publisher")
    print("=" * 70)
    print(f"Repository:   {repo}")
    print(f"Branch:       {branch}")
    print(f"Queue Dir:    {queue_dir.resolve()}")
    print(f"Posted Dir:   {posted_dir.resolve()}")
    print(f"Mode:         {'LOCAL VALIDATION' if args.validate_all else ('DRY RUN' if args.dry_run else 'LIVE API')}")
    print("=" * 70)

    # 1. Discover queued posts
    candidates = find_queued_posts(queue_dir)
    if not candidates:
        print(f"[Queue] No posts found in '{queue_dir}'. Nothing to post.")
        sys.exit(0)

    if args.validate_all:
        for candidate in candidates:
            validate_post(candidate)
            print(f"Validated {candidate.name}: {len(candidate.slides)} JPEG images")
        print(f"Local validation passed for {len(candidates)} posts. Hosted access and credentials were not tested.")
        return

    # 2. Select post
    selected_post: Optional[QueuedPost] = None
    if args.post:
        matches = [c for c in candidates if c.name == args.post or c.path.name == args.post]
        if not matches:
            print(f"Error: Post '{args.post}' not found in '{queue_dir}'.", file=sys.stderr)
            sys.exit(1)
        selected_post = matches[0]
    else:
        selected_post = candidates[0]

    validate_post(selected_post)
    state_path = posted_dir / "publication_state.json"
    previous = read_json(state_path).get(selected_post.name, {})
    history = read_json(posted_dir / "captions.json")
    if selected_post.name in history and not previous:
        raise RuntimeError(f"{selected_post.name} already appears in publication history; refusing to repost")
    if (posted_dir / selected_post.name).exists():
        raise RuntimeError(f"Archive destination already exists for {selected_post.name}; reconcile before publishing")

    # Verify caption
    if not selected_post.caption:
        print(
            f"Error: No caption found for post '{selected_post.name}'. "
            f"Ensure caption.txt exists inside the folder or captions.json is populated.",
            file=sys.stderr,
        )
        sys.exit(1)

    # 3. Build public raw.githubusercontent.com URLs for all slides
    slide_urls: List[str] = []
    for slide in selected_post.slides:
        rel_path = slide.resolve().relative_to(Path(__file__).resolve().parent).as_posix()
        slide_urls.append(build_raw_github_url(repo, branch, rel_path))

    # Print Post Details
    print(f"\n[Selected Post: {selected_post.name}]")
    print(f"  • Format:        {selected_post.post_type.upper()} ({len(selected_post.slides)} slide{'s' if len(selected_post.slides) > 1 else ''})")
    print(f"  • Path:          {selected_post.path}")
    print(f"  • Modified Time: {datetime.fromtimestamp(selected_post.mtime, tz=timezone.utc).isoformat()}")

    print("\n[Slides to Publish]")
    for idx, (slide, url) in enumerate(zip(selected_post.slides, slide_urls), 1):
        print(f"  Slide {idx}: {slide.name} -> {url}")

    print(f"\n[Caption Content]\n{'-' * 45}\n{selected_post.caption}\n{'-' * 45}\n")

    # 4. Handle Dry Run vs Live Run
    if args.dry_run:
        print("[DRY RUN] Status check of credentials:")
        print(f"  • IG_ACCESS_TOKEN: {'[PRESENT]' if access_token else '[MISSING/NOT SET]'}")
        print(f"  • IG_USER_ID:      {'[PRESENT] (' + user_id + ')' if user_id else '[MISSING/NOT SET]'}")

        print("\n[DRY RUN] Simulated API Calls that WOULD be executed:")
        if selected_post.post_type == "carousel":
            print(f"  1. For each of {len(slide_urls)} slides:")
            print(f"     POST {GRAPH_API_BASE}/me/media (payload: image_url, is_carousel_item=true)")
            print(f"     GET  {GRAPH_API_BASE}/<child_container_id>?fields=status_code,status (polling until FINISHED)")
            print(f"  2. POST {GRAPH_API_BASE}/me/media (payload: media_type=CAROUSEL, children=<child_ids>, caption=<{len(selected_post.caption)} chars>)")
            print(f"  3. GET  {GRAPH_API_BASE}/<carousel_id>?fields=status_code,status (polling until FINISHED)")
            print(f"  4. POST {GRAPH_API_BASE}/me/media_publish (payload: creation_id=<carousel_id>)")
        else:
            print(f"  1. POST {GRAPH_API_BASE}/me/media (payload: image_url, caption=<{len(selected_post.caption)} chars>)")
            print(f"  2. GET  {GRAPH_API_BASE}/<creation_id>?fields=status_code,status (polling until FINISHED)")
            print(f"  3. POST {GRAPH_API_BASE}/me/media_publish (payload: creation_id=<creation_id>)")

        print("\n[DRY RUN] Simulated File Movement that WOULD occur:")
        print(f"  • Move '{selected_post.path}' -> '{posted_dir / selected_post.name}'")
        print(f"  • Record post in '{posted_dir / 'captions.json'}'")
        if args.verify_hosted:
            verify_public_images(slide_urls, selected_post.slides)
        print("\nDRY RUN COMPLETE: Local images and caption validated. No Instagram API calls made.")
        sys.exit(0)

    # Live Mode
    if not access_token:
        print("Error: IG_ACCESS_TOKEN environment variable is missing.", file=sys.stderr)
        sys.exit(1)

    if not args.skip_token_refresh:
        refreshed = refresh_access_token(access_token, env_file_path=Path(".env"))
        if refreshed and "access_token" in refreshed:
            access_token = refreshed["access_token"]

    # 5. Publish
    def publish(before_publish):
        verify_public_images(slide_urls, selected_post.slides)
        kwargs = dict(caption=selected_post.caption, access_token=access_token,
                      user_id=user_id or None, before_publish=before_publish)
        if selected_post.post_type == "carousel":
            return post_carousel(slide_urls=slide_urls, **kwargs)
        return post_single_image(image_url=slide_urls[0], **kwargs)

    media_id = publish_once(selected_post, state_path, publish,
        lambda media: move_post_to_posted(selected_post, queue_dir, posted_dir, media))

    print(f"\n🎉 Successfully published {selected_post.name} (Media ID: {media_id}) and moved to {posted_dir}/!")


if __name__ == "__main__":
    main()
