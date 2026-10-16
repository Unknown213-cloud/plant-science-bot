#!/usr/bin/env python3
"""
Plant Science Bot - Topic Approval Manager
==========================================
Reads the latest research suggestions markdown report in suggestions/,
finds all ideas marked with a checked box (- [x] or - [X]), extracts the
structured topic data, and saves/appends them into topics.json so the
carousel generator can produce them.

Usage:
    python approve.py
    python approve.py --file suggestions/2026-10-16.md
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure utf-8 output encoding across Windows shells and CI environments
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def find_latest_suggestions_file(suggestions_dir: Path) -> Optional[Path]:
    """Find the newest suggestions report in suggestions/ directory."""
    if not suggestions_dir.exists() or not suggestions_dir.is_dir():
        return None

    files = [
        f for f in suggestions_dir.glob("*.md")
        if f.is_file() and not f.name.startswith(".")
    ]
    if not files:
        return None

    # Sort primarily by filename (YYYY-MM-DD.md), secondarily by mtime
    files.sort(key=lambda f: (f.stem, f.stat().st_mtime), reverse=True)
    return files[0]


def slugify(text: str) -> str:
    """Convert a headline into a clean URL/folder-safe identifier."""
    cleaned = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "-", cleaned).strip("-")


def parse_checked_ideas(md_content: str) -> List[Dict[str, Any]]:
    """
    Parse all ideas marked with `- [x]` or `- [X]` from the markdown report.
    Extracts headline, series, type, why timely, sources, and key facts.
    """
    approved_topics = []

    # Split into sections starting with `- [`
    # We look for `- [x]` or `- [X]`
    pattern = re.compile(
        r"-\s*\[([xX])\]\s*\*\*(\d+)\.\s*([^\*\n]+)\*\*(.*?)(?=(?:-\s*\[|\Z))",
        re.DOTALL,
    )

    for match in pattern.finditer(md_content):
        number_str = match.group(2).strip()
        headline = match.group(3).strip()
        block_text = match.group(4)

        # Extract Series
        series_match = re.search(r"-\s*\*\*Series:\*\*\s*(.+)", block_text)
        series = series_match.group(1).strip() if series_match else "Plant Science"

        # Extract Type
        type_match = re.search(r"-\s*\*\*Type:\*\*\s*(.+)", block_text)
        post_type = type_match.group(1).strip() if type_match else "Evergreen"

        # Extract Why It's Timely
        timely_match = re.search(r"-\s*\*\*Why It's Timely:\*\*\s*(.+)", block_text)
        timely_reason = timely_match.group(1).strip() if timely_match else ""

        # Extract Sources
        sources_match = re.search(r"-\s*\*\*Sources:\*\*\s*(.+)", block_text)
        sources_str = sources_match.group(1).strip() if sources_match else ""
        sources = [s.strip() for s in sources_str.split(",") if s.strip()] if sources_str else []

        # Extract Key Facts
        facts: List[str] = []
        fact_lines = re.findall(r"^\s*\d+\.\s*(.+)$", block_text, re.MULTILINE)
        for fl in fact_lines:
            cleaned_fact = fl.strip()
            if cleaned_fact:
                facts.append(cleaned_fact)

        topic_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d')}-{slugify(headline)}"

        approved_topics.append({
            "id": topic_id,
            "rank_number": int(number_str),
            "headline": headline,
            "series": series,
            "type": post_type,
            "timely_reason": timely_reason,
            "sources": sources,
            "facts": facts,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "status": "approved",
        })

    return approved_topics


def load_topics(topics_path: Path) -> List[Dict[str, Any]]:
    """Load existing topics from topics.json."""
    if not topics_path.exists():
        return []
    try:
        with open(topics_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                return data.get("topics", [])
            return []
    except Exception as e:
        print(f"Warning: Failed to parse {topics_path}: {e}", file=sys.stderr)
        return []


def save_topics(topics_path: Path, topics: List[Dict[str, Any]]) -> None:
    """Save topics list to topics.json with neat indentation."""
    topics_path.parent.mkdir(parents=True, exist_ok=True)
    with open(topics_path, "w", encoding="utf-8") as f:
        json.dump(topics, f, indent=2, ensure_ascii=False)
        f.write("\n")


def main():
    parser = argparse.ArgumentParser(
        description="Plant Science Bot: Approve research suggestions and export them into topics.json."
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help="Path to specific suggestions markdown file (default: newest in suggestions/).",
    )
    parser.add_argument(
        "--suggestions-dir",
        type=Path,
        default=Path("suggestions"),
        help="Directory where suggestions reports are saved (default: suggestions).",
    )
    parser.add_argument(
        "--topics-file",
        type=Path,
        default=Path("topics.json"),
        help="Destination JSON file for approved topics (default: topics.json).",
    )

    args = parser.parse_args()

    # 1. Determine suggestions file to read
    suggestions_file = args.file
    if not suggestions_file:
        suggestions_file = find_latest_suggestions_file(args.suggestions_dir)

    if not suggestions_file or not suggestions_file.exists():
        print(f"Error: No suggestions file found in '{args.suggestions_dir}'. Run python research.py first.", file=sys.stderr)
        sys.exit(1)

    print("=" * 70)
    print("🌿 Plant Science Bot - Topic Approval Manager")
    print("=" * 70)
    print(f"Reading File:     {suggestions_file.resolve()}")
    print(f"Destination:      {args.topics_file.resolve()}")
    print("=" * 70)

    # 2. Parse suggestions file for ticked checkboxes
    content = suggestions_file.read_text(encoding="utf-8")
    checked_topics = parse_checked_ideas(content)

    if not checked_topics:
        print(f"\n[Notice] No checked items found in {suggestions_file.name}.")
        print("To approve an idea:")
        print(f"  1. Open '{suggestions_file.resolve()}'")
        print("  2. Replace '- [ ]' with '- [x]' next to your chosen idea(s)")
        print("  3. Run 'python approve.py' again.")
        sys.exit(0)

    # 3. Load existing topics and append new ones without duplicates
    existing_topics = load_topics(args.topics_file)
    existing_headlines = {t.get("headline", "").lower().strip() for t in existing_topics}

    added_count = 0
    updated_count = 0

    print(f"\n[Found {len(checked_topics)} Checked Topic(s)]")
    for topic in checked_topics:
        hl_key = topic["headline"].lower().strip()
        print(f"  • {topic['headline']} ({topic['type']} | {topic['series']})")
        if hl_key in existing_headlines:
            # Update existing
            for idx, et in enumerate(existing_topics):
                if et.get("headline", "").lower().strip() == hl_key:
                    existing_topics[idx] = topic
                    updated_count += 1
                    break
        else:
            existing_topics.append(topic)
            existing_headlines.add(hl_key)
            added_count += 1

    # 4. Save to topics.json
    save_topics(args.topics_file, existing_topics)

    print(f"\n🎉 Successfully saved to {args.topics_file.name}!")
    print(f"   • Newly Added:   {added_count}")
    print(f"   • Updated:       {updated_count}")
    print(f"   • Total Active:  {len(existing_topics)}")
    print(f"\nThe carousel generator can now consume '{args.topics_file.name}' to generate slides.")


if __name__ == "__main__":
    main()
