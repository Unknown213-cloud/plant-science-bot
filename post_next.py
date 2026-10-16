#!/usr/bin/env python3
"""
Plant Science Bot - Automated Instagram Publisher
=================================================
Fetches the oldest image from the queue/ folder, builds its public
raw.githubusercontent.com URL, posts it to Instagram via the Instagram
Graph API with Instagram Login, and moves the published media and caption
to posted/.

Requirements:
    - Environment variables:
        IG_ACCESS_TOKEN: Long-lived Instagram User Access Token
        IG_USER_ID: Instagram User ID (for the Creator/Business profile)
    - Optional:
        GITHUB_REPOSITORY: 'owner/repo' (defaults to git config or Unknown213-cloud/plant-science-bot)
        GITHUB_REF_NAME: branch name (defaults to 'main')
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

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


def get_git_repo_info() -> Tuple[str, str]:
    """
    Detect the GitHub repository ('owner/repo') and current branch name.
    Prioritizes GitHub Actions environment variables, then falls back
    to local git commands, and finally defaults.
    """
    # 1. Environment variables (set automatically in GitHub Actions)
    repo = os.getenv("GITHUB_REPOSITORY")
    branch = os.getenv("GITHUB_REF_NAME")

    if not repo:
        try:
            url_proc = subprocess.run(
                ["git", "config", "--get", "remote.origin.url"],
                capture_output=True,
                text=True,
                check=False,
            )
            raw_url = url_proc.stdout.strip()
            if raw_url:
                # Handle git@github.com:owner/repo.git or https://github.com/owner/repo.git
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
            )
            detected_branch = branch_proc.stdout.strip()
            if detected_branch and detected_branch != "HEAD":
                branch = detected_branch
        except Exception:
            pass

    return (repo or DEFAULT_REPO, branch or DEFAULT_BRANCH)


def find_oldest_image(queue_dir: Path) -> Optional[Path]:
    """
    Find the oldest image in the queue directory based on file modification time.
    Ties are broken by alphabetical sorting for deterministic selection.
    """
    if not queue_dir.exists() or not queue_dir.is_dir():
        return None

    candidates = [
        p for p in queue_dir.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
    ]

    if not candidates:
        return None

    # Sort primarily by mtime (oldest first), secondarily by filename
    candidates.sort(key=lambda p: (p.stat().st_mtime, p.name))
    return candidates[0]


def load_captions(captions_path: Path) -> Dict[str, str]:
    """
    Load captions mapping from captions.json.
    Supports either string values or objects with a 'caption'/'text' field.
    """
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
        print(f"Warning: Failed to parse captions file at {captions_path}: {e}", file=sys.stderr)
        return {}


def save_captions(captions_path: Path, data: dict) -> None:
    """Save dictionary to captions.json with neat indentation."""
    captions_path.parent.mkdir(parents=True, exist_ok=True)
    with open(captions_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def build_raw_github_url(repo: str, branch: str, file_rel_path: str) -> str:
    """
    Build the public raw.githubusercontent.com URL for a repository asset.
    """
    normalized_path = file_rel_path.replace("\\", "/").lstrip("/")
    # URL encode filename while preserving path slashes
    parts = [urllib.parse.quote(part) for part in normalized_path.split("/")]
    encoded_path = "/".join(parts)
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{encoded_path}"


def refresh_access_token(access_token: str, env_file_path: Optional[Path] = None) -> Optional[dict]:
    """
    Refresh a long-lived Instagram user access token via:
    GET https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token={access_token}
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
                print("[Token Info] Token is active and was generated/refreshed within the last 24 hours (refresh only needed every 24h+).")
            else:
                print(f"[Token Notice] Could not refresh token ({res_data}). Continuing with current token.", file=sys.stderr)
            return None

        new_token = res_data["access_token"]
        expires_in = res_data.get("expires_in", 0)
        days_left = expires_in // 86400

        print(f"[Token Success] Token successfully refreshed! Valid for ~{days_left} days ({expires_in}s).")

        # Optionally update local .env file if it exists
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
        print(f"[Token Warning] Exception during token refresh: {e}", file=sys.stderr)
        return None


def poll_media_container_status(creation_id: str, access_token: str, max_wait_sec: int = 40) -> bool:
    """
    Poll the status of an Instagram media container until it is ready for publishing.
    """
    url = f"{GRAPH_API_BASE}/{creation_id}"
    params = {
        "fields": "status_code,status",
        "access_token": access_token,
    }

    start_time = time.time()
    while time.time() - start_time < max_wait_sec:
        try:
            res = requests.get(url, params=params, timeout=15)
            if res.status_code == 200:
                data = res.json()
                status_code = data.get("status_code")
                if status_code == "FINISHED":
                    print(f"[API] Media container {creation_id} processing complete.")
                    return True
                elif status_code == "ERROR":
                    print(f"[API Error] Media container error: {data}", file=sys.stderr)
                    return False
                elif status_code == "IN_PROGRESS":
                    print(f"[API] Media container processing in progress, waiting...")
                else:
                    # If field is omitted or different status, assume ready
                    return True
        except Exception as e:
            print(f"[API Warning] Container status check warning: {e}")

        time.sleep(3)

    print("[API Warning] Container status polling timed out, attempting publish anyway...")
    return True


def post_to_instagram(
    image_url: str,
    caption: str,
    access_token: str,
    user_id: Optional[str] = None,
) -> str:
    """
    Publishes an image to Instagram via Instagram Login:
      1. POST https://graph.instagram.com/me/media (or /{user_id}/media)
         payload: image_url, caption, access_token
      2. Poll container status until FINISHED
      3. POST https://graph.instagram.com/me/media_publish (or /{user_id}/media_publish)
         payload: creation_id, access_token
    """
    # Determine base endpoint path (graph.instagram.com/me/media by default as required)
    container_endpoint = f"{GRAPH_API_BASE}/me/media"
    publish_endpoint = f"{GRAPH_API_BASE}/me/media_publish"

    print(f"[API] Creating media container at {container_endpoint}...")
    container_payload = {
        "image_url": image_url,
        "caption": caption,
        "access_token": access_token,
    }

    resp = requests.post(container_endpoint, data=container_payload, timeout=30)
    data = resp.json()

    # Fallback to /{user_id}/media if 'me' endpoint returns an error recommending user ID
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

    # Wait for Instagram to fetch and process image
    poll_media_container_status(creation_id, access_token)

    # Publish the container
    print(f"[API] Publishing container at {publish_endpoint}...")
    publish_payload = {
        "creation_id": creation_id,
        "access_token": access_token,
    }

    pub_resp = requests.post(publish_endpoint, data=publish_payload, timeout=30)
    pub_data = pub_resp.json()

    if pub_resp.status_code != 200 or "id" not in pub_data:
        raise RuntimeError(f"Instagram Media Publish failed [{pub_resp.status_code}]: {pub_data}")

    media_id = pub_data["id"]
    print(f"[API Success] Published successfully! Media ID: {media_id}")
    return media_id


def move_files_to_posted(
    image_file: Path,
    queue_captions_file: Path,
    posted_dir: Path,
    posted_captions_file: Path,
    caption_text: str,
    media_id: Optional[str] = None,
) -> None:
    """
    Move the published image to posted/ directory and update captions.json.
    """
    posted_dir.mkdir(parents=True, exist_ok=True)
    destination_img = posted_dir / image_file.name

    print(f"[Storage] Moving {image_file} -> {destination_img}...")
    shutil.move(str(image_file), str(destination_img))

    # Update queue/captions.json
    if queue_captions_file.exists():
        queue_data = {}
        try:
            with open(queue_captions_file, "r", encoding="utf-8") as f:
                queue_data = json.load(f)
        except Exception:
            queue_data = {}

        if image_file.name in queue_data:
            del queue_data[image_file.name]
            save_captions(queue_captions_file, queue_data)
            print(f"[Storage] Removed '{image_file.name}' from {queue_captions_file.name}.")

    # Update posted/captions.json
    posted_data = {}
    if posted_captions_file.exists():
        try:
            with open(posted_captions_file, "r", encoding="utf-8") as f:
                posted_data = json.load(f)
        except Exception:
            posted_data = {}

    posted_data[image_file.name] = {
        "caption": caption_text,
        "posted_at": datetime.now(timezone.utc).isoformat(),
        "media_id": media_id or "dry-run",
    }
    save_captions(posted_captions_file, posted_data)
    print(f"[Storage] Recorded '{image_file.name}' in {posted_captions_file.name}.")


def main():
    parser = argparse.ArgumentParser(
        description="Plant Science Bot: Automatically post queued infographics to Instagram."
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
        default=Path("queue"),
        help="Directory containing queued post images and captions.json (default: queue).",
    )
    parser.add_argument(
        "--posted-dir",
        type=Path,
        default=Path("posted"),
        help="Directory where posted images and history are archived (default: posted).",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=None,
        help="GitHub repo in 'owner/repo' format (default: auto-detected from environment/git).",
    )
    parser.add_argument(
        "--branch",
        type=str,
        default=None,
        help="GitHub branch name for raw.githubusercontent.com URLs (default: main).",
    )

    args = parser.parse_args()

    # Load credentials from environment
    access_token = os.getenv("IG_ACCESS_TOKEN", "").strip()
    user_id = os.getenv("IG_USER_ID", "").strip()

    # Handle standalone token refresh if requested
    if args.refresh_token:
        if not access_token:
            print("Error: IG_ACCESS_TOKEN environment variable is required to refresh token.", file=sys.stderr)
            sys.exit(1)
        res = refresh_access_token(access_token, env_file_path=Path(".env"))
        sys.exit(0 if res else 1)

    # Detect repo & branch for constructing raw.githubusercontent.com URLs
    detected_repo, detected_branch = get_git_repo_info()
    repo = args.repo or detected_repo
    branch = args.branch or detected_branch

    queue_dir = args.queue_dir
    posted_dir = args.posted_dir
    queue_captions_path = queue_dir / "captions.json"
    posted_captions_path = posted_dir / "captions.json"

    print("=" * 65)
    print("🌿 Plant Science Bot - Daily Instagram Publisher")
    print("=" * 65)
    print(f"Repository:  {repo}")
    print(f"Branch:      {branch}")
    print(f"Queue Dir:   {queue_dir.resolve()}")
    print(f"Posted Dir:  {posted_dir.resolve()}")
    print(f"Dry Run:     {'YES (Simulation Mode)' if args.dry_run else 'NO (Live API Mode)'}")
    print("=" * 65)

    # 1. Identify oldest image in queue/
    oldest_image = find_oldest_image(queue_dir)
    if not oldest_image:
        print(f"[Queue] No images found in '{queue_dir}'. Nothing to post.")
        sys.exit(0)

    # 2. Match caption from captions.json
    captions_map = load_captions(queue_captions_path)
    caption = captions_map.get(oldest_image.name, "").strip()

    if not caption:
        print(
            f"Error: No matching caption found for '{oldest_image.name}' in {queue_captions_path}.",
            file=sys.stderr,
        )
        sys.exit(1)

    # 3. Build public raw.githubusercontent.com URL
    rel_image_path = f"{queue_dir.name}/{oldest_image.name}"
    public_url = build_raw_github_url(repo, branch, rel_image_path)

    print(f"\n[Selected Post]")
    print(f"  • Image File:    {oldest_image.name}")
    print(f"  • Modified Time: {datetime.fromtimestamp(oldest_image.stat().st_mtime, tz=timezone.utc).isoformat()}")
    print(f"  • Public URL:    {public_url}")
    print(f"\n[Caption Content]\n{'-' * 40}\n{caption}\n{'-' * 40}\n")

    # 4. Handle Dry Run vs Live Run
    if args.dry_run:
        print("[DRY RUN] Status check of credentials:")
        print(f"  • IG_ACCESS_TOKEN: {'[PRESENT]' if access_token else '[MISSING/NOT SET]'}")
        print(f"  • IG_USER_ID:      {'[PRESENT] (' + user_id + ')' if user_id else '[MISSING/NOT SET]'}")
        print("\n[DRY RUN] Simulated API Calls that WOULD be executed:")
        print(f"  1. POST {GRAPH_API_BASE}/me/media")
        print(f"     Payload: {{'image_url': '{public_url}', 'caption': '<{len(caption)} chars>', 'access_token': '***'}}")
        print(f"  2. GET  {GRAPH_API_BASE}/<creation_id>?fields=status_code,status")
        print(f"  3. POST {GRAPH_API_BASE}/me/media_publish")
        print(f"     Payload: {{'creation_id': '<creation_id>', 'access_token': '***'}}")
        print("\n[DRY RUN] Simulated File Movement that WOULD occur:")
        print(f"  • Move '{oldest_image}' -> '{posted_dir / oldest_image.name}'")
        print(f"  • Remove '{oldest_image.name}' from '{queue_captions_path}'")
        print(f"  • Add entry to '{posted_captions_path}'")
        print("\n✅ DRY RUN COMPLETE: No live requests made, no files modified.")
        sys.exit(0)

    # Live Mode: verify credentials
    if not access_token:
        print("Error: IG_ACCESS_TOKEN environment variable is missing.", file=sys.stderr)
        sys.exit(1)

    # Check and refresh token before posting to ensure it is always fresh
    try:
        refreshed = refresh_access_token(access_token, env_file_path=Path(".env"))
        if refreshed and "access_token" in refreshed:
            access_token = refreshed["access_token"]
    except Exception as e:
        print(f"[Token Warning] Refresh check exception (continuing with existing token): {e}")

    # 5. Publish to Instagram
    media_id = post_to_instagram(
        image_url=public_url,
        caption=caption,
        access_token=access_token,
        user_id=user_id if user_id else None,
    )

    # 6. Move files to posted/
    move_files_to_posted(
        image_file=oldest_image,
        queue_captions_file=queue_captions_path,
        posted_dir=posted_dir,
        posted_captions_file=posted_captions_path,
        caption_text=caption,
        media_id=media_id,
    )

    print(f"\n🎉 Successfully posted {oldest_image.name} (Media ID: {media_id}) and moved to {posted_dir}/!")


if __name__ == "__main__":
    main()
