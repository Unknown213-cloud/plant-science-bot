#!/usr/bin/env python3
"""
Automated Batch Image Generator for AI Agents
==============================================
Reads `prompts/batch_human_anatomy_20.json` and generates the 20 raw images
into `raw_batch/` using Google Gemini / Imagen API (or any configured key).

Usage:
    python run_agent_generation.py
    python run_agent_generation.py --api-key YOUR_GEMINI_KEY
    python run_agent_generation.py --output-dir ../raw_batch
"""

import argparse
import json
import os
import sys
import time

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import requests
except ImportError:
    print("Error: 'requests' is required. Install via 'pip install requests'.", file=sys.stderr)
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
DEFAULT_JSON = os.path.join(SCRIPT_DIR, "batch_human_anatomy_20.json")
DEFAULT_OUT = os.path.join(REPO_ROOT, "raw_batch")


def parse_args():
    parser = argparse.ArgumentParser(description="Generate 20 raw AI images from prompt book.")
    parser.add_argument("--json", default=DEFAULT_JSON, help="Path to batch prompts JSON file")
    parser.add_argument("--output-dir", default=DEFAULT_OUT, help="Output directory for raw images")
    parser.add_argument("--api-key", default=os.getenv("GEMINI_API_KEY"), help="Gemini API Key")
    parser.add_argument("--skip-existing", action="store_true", default=True, help="Skip files that already exist")
    return parser.parse_args()


def generate_with_gemini_rest(prompt: str, api_key: str, out_path: str, max_retries: int = 3) -> bool:
    """
    Call Google Gemini Imagen REST API endpoint to generate high-resolution image.
    Handles rate limits (429) with exponential backoff.
    """
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict?key={api_key}"
    payload = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "aspectRatio": "3:4",
            "outputMimeType": "image/png",
            "sampleCount": 1
        }
    }

    headers = {"Content-Type": "application/json"}

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                predictions = data.get("predictions", [])
                if predictions and "bytesBase64Encoded" in predictions[0]:
                    import base64
                    raw_bytes = base64.b64decode(predictions[0]["bytesBase64Encoded"])
                    with open(out_path, "wb") as f:
                        f.write(raw_bytes)
                    return True
                else:
                    print(f"    [Warning] No image bytes returned in response: {data}")
            elif resp.status_code == 429:
                wait_time = attempt * 30
                print(f"    [Rate Limit 429] Waiting {wait_time}s before retry (attempt {attempt}/{max_retries})...")
                time.sleep(wait_time)
            else:
                print(f"    [Error {resp.status_code}] {resp.text}")
                time.sleep(5)
        except Exception as e:
            print(f"    [Exception] {e}")
            time.sleep(5)

    return False


def main():
    args = parse_args()

    if not os.path.exists(args.json):
        print(f"Error: Prompt book JSON not found at '{args.json}'.", file=sys.stderr)
        sys.exit(1)

    with open(args.json, "r", encoding="utf-8") as f:
        data = json.load(f)

    os.makedirs(args.output_dir, exist_ok=True)

    print("=" * 70)
    print(f"🎨 Generating Batch: {data.get('batch_name', 'Science Batch')}")
    print(f"📁 Output Directory: {args.output_dir}")
    print(f"📊 Total Images:     {data.get('total_images', 20)}")
    print("=" * 70)

    api_key = args.api_key
    if not api_key:
        print("\n⚠️  No GEMINI_API_KEY provided in arguments or .env.")
        print("    If you are giving this file to an external agent:")
        print("    1. Provide the prompts from 'prompts/batch_human_anatomy_20.json' or 'prompts/PROMPT_BOOK.md'")
        print("    2. Place generated image files directly into 'raw_batch/' matching the target filenames.")
        print("    3. Then run 'python build_carousel_batch.py' to assemble all carousels.")
        return

    success_count = 0
    total_count = 0

    for post in data.get("posts", []):
        print(f"\n▶ Post: {post.get('topic')} ({post.get('category')})")
        for slide in post.get("slides", []):
            total_count += 1
            filename = slide.get("filename")
            out_file = os.path.join(args.output_dir, filename)
            prompt = slide.get("prompt")
            subject = slide.get("subject")

            if args.skip_existing and os.path.exists(out_file) and os.path.getsize(out_file) > 10000:
                print(f"  [Skipped] {filename} (already exists)")
                success_count += 1
                continue

            print(f"  Generating Slide {slide.get('slide_number')}: {subject} -> {filename}...")
            ok = generate_with_gemini_rest(prompt, api_key, out_file)
            if ok:
                size_kb = os.path.getsize(out_file) // 1024
                print(f"    ✓ Saved {filename} ({size_kb} KB)")
                success_count += 1
            else:
                print(f"    ✗ Failed to generate {filename}")

            # Politeness delay to prevent rate limits
            time.sleep(2)

    print("\n" + "=" * 70)
    print(f"🎉 Batch Generation Complete: {success_count} / {total_count} images ready in '{args.output_dir}'")
    print("Next Step: Run 'python build_carousel_batch.py' to composite slides & captions!")
    print("=" * 70)


if __name__ == "__main__":
    main()
