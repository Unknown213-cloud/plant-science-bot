"""Validation and durable publication checkpoints shared by local and CI runs."""
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parent


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def validate_post(post):
    if not post.caption.strip() or len(post.caption) > 2200:
        raise ValueError(f"{post.name}: caption must contain 1–2200 characters")
    if not 1 <= len(post.slides) <= 10:
        raise ValueError(f"{post.name}: expected 1–10 images")
    sizes = set()
    for slide in post.slides:
        with Image.open(slide) as image:
            image.load()
            if image.format != "JPEG" or image.mode != "RGB":
                raise ValueError(f"{slide}: publishing requires RGB JPEG; rebuild the carousel")
            width, height = image.size
            if not 320 <= width <= 1440 or not 0.8 <= width / height <= 1.91:
                raise ValueError(f"{slide}: unsupported dimensions {image.size}")
            sizes.add(image.size)
        if slide.stat().st_size > 8 * 1024 * 1024:
            raise ValueError(f"{slide}: exceeds 8 MB")
    if len(sizes) != 1:
        raise ValueError(f"{post.name}: carousel dimensions must match")


def post_fingerprint(post):
    digest = hashlib.sha256(post.caption.encode("utf-8"))
    for slide in post.slides:
        digest.update(slide.name.encode("utf-8"))
        digest.update(slide.read_bytes())
    return digest.hexdigest()


def verify_public_images(urls, slides):
    """Meta needs anonymous access; verify exact bytes, not just HTTP status."""
    for url, slide in zip(urls, slides):
        response = requests.get(url, timeout=30)
        if response.status_code != 200:
            raise RuntimeError(f"Image is not publicly accessible ({response.status_code}): {url}")
        if response.content != slide.read_bytes():
            raise RuntimeError(f"Hosted image differs from local image: {url}. Commit and push first.")


def checkpoint(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    if os.getenv("GITHUB_ACTIONS") == "true":
        # Persist BEFORE sending media_publish. A runner crash must not repost.
        relative = str(path.resolve().relative_to(ROOT))
        subprocess.run(["git", "add", "--", relative], cwd=ROOT, check=True)
        changed = subprocess.run(["git", "diff", "--cached", "--quiet", "--", relative], cwd=ROOT)
        if changed.returncode == 1:
            subprocess.run(["git", "commit", "-m", "Record publication checkpoint [skip ci]", "--", relative], cwd=ROOT, check=True)
        elif changed.returncode != 0:
            raise RuntimeError("Could not inspect publication checkpoint")
        subprocess.run(["git", "push", "origin", "HEAD"], cwd=ROOT, check=True)


def publish_once(post, state_path, publish, archive):
    state = read_json(state_path)
    previous = state.get(post.name, {})
    fingerprint = post_fingerprint(post)
    if previous:
        if previous.get("fingerprint") != fingerprint:
            raise RuntimeError(f"{post.name}: content changed after publication started; review the journal")
        if previous.get("status") == "published":
            archive(previous["media_id"])
            return previous["media_id"]
        raise RuntimeError(f"{post.name}: prior publish outcome is uncertain. Reconcile publication_state.json with Instagram before retrying.")

    def before_publish(creation_id):
        state[post.name] = {"status": "publishing", "creation_id": creation_id,
                            "fingerprint": fingerprint, "updated_at": datetime.now(timezone.utc).isoformat()}
        checkpoint(state_path, state)

    media_id = publish(before_publish)
    state[post.name].update(status="published", media_id=media_id,
                            updated_at=datetime.now(timezone.utc).isoformat())
    checkpoint(state_path, state)
    archive(media_id)
    return media_id
