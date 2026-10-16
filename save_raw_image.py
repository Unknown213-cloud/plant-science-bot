#!/usr/bin/env python3
import os
import sys
from PIL import Image

TARGET_DIRS = [
    r"d:\insta bot\plant-science-bot\raw_batch",
    r"d:\insta bot\raw_batch"
]

def save_image(src_path: str, filename: str):
    if not os.path.exists(src_path):
        print(f"[Error] Source image {src_path} does not exist!", file=sys.stderr)
        return False
    
    try:
        with Image.open(src_path) as img:
            for out_dir in TARGET_DIRS:
                os.makedirs(out_dir, exist_ok=True)
                dest = os.path.join(out_dir, filename)
                img.save(dest, "PNG", quality=95)
                print(f"[Saved] {dest} ({img.size[0]}x{img.size[1]})")
        return True
    except Exception as e:
        print(f"[Error] Failed to process {src_path}: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: save_raw_image.py <source_path> <target_filename.png>")
        sys.exit(1)
    
    src = sys.argv[1]
    name = sys.argv[2]
    if not name.endswith(".png"):
        name += ".png"
    
    success = save_image(src, name)
    sys.exit(0 if success else 1)
