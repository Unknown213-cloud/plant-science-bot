#!/usr/bin/env python3
"""
Batch Publisher & GitHub Sync Tool
===================================
1. Runs post_next.py in dry-run mode to verify Meta Graph API compliance.
2. Formats release notes and status summary.
3. Stages and commits files with a clean commit message.
4. Pushes to GitHub if --push flag is provided.

Usage:
    python publish_batch.py          # Dry run and verify only
    python publish_batch.py --push   # Commit and push to GitHub
"""

import argparse
import os
import subprocess
import sys

# Ensure utf-8 output encoding across Windows shells
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLISH_PATHS = [
    "queue/", "posted/", "preview.html", "codex_generate_raw/", "prompts/",
    ".github/", ".gitignore", ".env.example", "README.md", "AUTOMATION_AUDIT.md",
    "requirements.txt", "requirements-publish.txt", "post_next.py", "publication.py",
    "refresh_ci_token.py", "build_carousel_batch.py", "build_preview.js", "publish_batch.py",
    "research.py", "approve.py", "topics.json", "suggestions/", "tests/",
]


def run_cmd(cmd, check=True):
    print(f"▶ Running: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=REPO_DIR, capture_output=True, text=True, check=False)
    if res.stdout:
        print(res.stdout.strip())
    if res.stderr and res.returncode != 0:
        print(res.stderr.strip(), file=sys.stderr)
    if check and res.returncode != 0:
        sys.exit(res.returncode)
    return res


def main():
    parser = argparse.ArgumentParser(description="Verify and publish queued carousel batch to GitHub.")
    parser.add_argument("--push", action="store_true", help="Commit and push changes to remote repository")
    args = parser.parse_args()

    print("=" * 70)
    print("🚀 Publishing Pipeline: Batch Verification & Sync")
    print("=" * 70)

    # 1. Verification with post_next.py dry-run
    print("\n[Step 1/3] Validating every queued image and caption locally...")
    python_exe = sys.executable
    dry_run_res = subprocess.run([python_exe, "post_next.py", "--validate-all"], cwd=REPO_DIR, text=True)
    if dry_run_res.returncode != 0:
        print("\n❌ Error: post_next.py dry-run failed. Resolve issues before pushing.", file=sys.stderr)
        sys.exit(1)

    print("\n[Step 2/3] Checking Git Status...")
    paths = [p for p in PUBLISH_PATHS if os.path.exists(os.path.join(REPO_DIR, p))]
    status_res = run_cmd(["git", "status", "--porcelain", "--", *paths])
    if not status_res.stdout.strip():
        print("Notice: No unstaged or untracked changes in queue/ or preview.html.")
        return

    # 3. Stage, commit, and push if requested
    if not args.push:
        print("\n" + "=" * 70)
        print("ℹ️  Dry-run verification passed successfully!")
        print("To stage, commit, and push this batch to GitHub, run:")
        print("    python publish_batch.py --push")
        print("=" * 70)
        return

    print("\n[Step 3/3] Staging, committing, and pushing to GitHub...")
    run_cmd(["git", "add", "--", *paths])
    commit_msg = "fix: harden scheduled publishing and queue Codex anatomy batch"
    run_cmd(["git", "commit", "-m", commit_msg])
    run_cmd(["git", "push"])

    print("\n" + "=" * 70)
    print("🎉 Successfully pushed carousel batch to GitHub!")
    print("Scheduled publishing will execute via GitHub Actions on Mon/Wed/Fri/Sun at 13:00 UTC.")
    print("=" * 70)


if __name__ == "__main__":
    main()
