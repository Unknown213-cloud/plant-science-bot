#!/usr/bin/env python3
"""
Master Carousel Batch Compositor
=================================
Consumes 20 raw images from `raw_batch/`, renders Pillow typography,
generates 4:5 carousels in `queue/`, writes verified captions and facts_check.md,
and updates `preview.html`.

Usage:
    python build_carousel_batch.py
"""

import os
import shutil
import subprocess
import sys
import argparse
import tempfile
from pathlib import Path
from datetime import datetime, timezone

# Ensure utf-8 output encoding across Windows shells
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from PIL import Image, ImageDraw, ImageFont

CANVAS_W = 1080
CANVAS_H = 1350

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(REPO_DIR, "codex_generate_raw")
QUEUE_DIR = os.path.join(REPO_DIR, "queue")
ARCHIVE_DIR = os.path.join(REPO_DIR, "posted", "previous_batches")

# Fonts
FONT_DIR = r"C:\Windows\Fonts"
def find_font(*candidates):
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    raise RuntimeError("No usable font found. Install fonts-dejavu-core on Linux.")

font_bold = find_font(os.path.join(FONT_DIR, "segoeuib.ttf"), os.path.join(FONT_DIR, "arialbd.ttf"),
                      "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
font_reg = find_font(os.path.join(FONT_DIR, "segoeui.ttf"), os.path.join(FONT_DIR, "arial.ttf"),
                     "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
font_semi = font_bold

f_badge = ImageFont.truetype(font_semi, 22)
f_headline = ImageFont.truetype(font_bold, 52)
f_subhead = ImageFont.truetype(font_reg, 24)
f_fact_num = ImageFont.truetype(font_bold, 20)
f_title = ImageFont.truetype(font_bold, 38)
f_body = ImageFont.truetype(font_reg, 27)
f_footer = ImageFont.truetype(font_reg, 20)
f_footnote = ImageFont.truetype(font_reg, 16)


def fitted_text(draw, position, text, font, fill, spacing=4):
    """Fit each text block inside the slide's right safe margin."""
    available = CANVAS_W - (95 if position[0] == 95 else 64) - position[0]
    while max(font.getlength(line) for line in text.splitlines()) > available:
        if font.size <= 18:
            raise ValueError(f"Text cannot fit at readable size: {text}")
        font = font.font_variant(size=font.size - 1)
    draw.text(position, text, font=font, fill=fill, spacing=spacing)


def save_slide(image, out_path):
    image.convert("RGB").save(out_path, "JPEG", quality=94, subsampling=0, optimize=True)


def draw_pill(draw, box, fill_color, border_color, radius=16, border_width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill_color, outline=border_color, width=border_width)


def create_base_canvas(img_path, focus_crop="center", zoom=1.0):
    canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), (4, 7, 10, 255))
    src = Image.open(img_path).convert("RGBA")
    sw, sh = src.size

    scale = max(CANVAS_W / sw, (CANVAS_H * 0.84) / sh) * zoom
    nw, nh = int(sw * scale), int(sh * scale)
    src_resized = src.resize((nw, nh), Image.Resampling.LANCZOS)

    ox = (CANVAS_W - nw) // 2
    if focus_crop == "top":
        oy = int(CANVAS_H * 0.08)
    elif focus_crop == "bottom":
        oy = CANVAS_H - nh - 30
    elif focus_crop == "center_high":
        oy = (CANVAS_H - nh) // 2 - 40
    else:
        oy = (CANVAS_H - nh) // 2 + 20

    canvas.paste(src_resized, (ox, oy), src_resized)

    # Top gradient for readable title/badges
    top_grad = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    d_top = ImageDraw.Draw(top_grad)
    for y in range(340):
        alpha = int(245 * (1.0 - (y / 340) ** 1.3))
        d_top.line([(0, y), (CANVAS_W, y)], fill=(4, 7, 10, alpha))
    canvas = Image.alpha_composite(canvas, top_grad)

    # Bottom gradient for readable text card
    bot_grad = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    d_bot = ImageDraw.Draw(bot_grad)
    for y in range(CANVAS_H - 490, CANVAS_H):
        dist = y - (CANVAS_H - 490)
        alpha = int(250 * ((dist / 490) ** 1.1))
        d_bot.line([(0, y), (CANVAS_W, y)], fill=(4, 7, 10, alpha))
    canvas = Image.alpha_composite(canvas, bot_grad)

    return canvas


def draw_header(draw, category, slide_str, accent_color=(46, 213, 115)):
    cat_text = category.upper()
    cat_w = f_badge.getbbox(cat_text)[2]
    pill_box = (60, 55, 60 + cat_w + 50, 95)
    draw_pill(draw, pill_box, (10, 16, 24, 220), (*accent_color, 160), radius=18, border_width=1)
    draw.ellipse((76, 69, 88, 81), fill=(*accent_color, 255))
    fitted_text(draw, (98, 63), cat_text, font=f_badge, fill=(235, 245, 242, 255))

    c_w = f_badge.getbbox(slide_str)[2]
    c_box = (CANVAS_W - 60 - c_w - 36, 55, CANVAS_W - 60, 95)
    draw_pill(draw, c_box, (15, 20, 26, 200), (255, 255, 255, 50), radius=18, border_width=1)
    fitted_text(draw, (c_box[0] + 18, 63), slide_str, font=f_badge, fill=(180, 200, 210, 255))


def draw_footer(draw, next_hint="swipe →", show_ai_note=False):
    fitted_text(draw, (64, CANVAS_H - 68), "@plantscience.bot", font=f_footer, fill=(130, 150, 160, 200))
    if next_hint:
        h_w = f_footer.getbbox(next_hint)[2]
        fitted_text(draw, (CANVAS_W - 64 - h_w, CANVAS_H - 68), next_hint, font=f_footer, fill=(190, 220, 210, 230))
    if show_ai_note:
        ai_w = f_footnote.getbbox("AI illustration")[2]
        fitted_text(draw, (CANVAS_W - 64 - ai_w, CANVAS_H - 66), "AI illustration", font=f_footnote, fill=(145, 160, 170, 190))


def build_slide_1(raw_path, out_path, cat, headline_lines, teaser_title, teaser_body, accent, light_accent):
    canvas = create_base_canvas(raw_path, focus_crop="top", zoom=1.0)
    overlay = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    draw_header(draw, cat, "01 / 05", accent_color=accent)

    y_text = 135
    for i, line in enumerate(headline_lines):
        color = (255, 255, 255, 255) if i == 0 else (*light_accent, 255)
        fitted_text(draw, (64, y_text), line, font=f_headline, fill=color)
        y_text += 65

    card_box = (60, CANVAS_H - 330, CANVAS_W - 60, CANVAS_H - 95)
    draw_pill(draw, card_box, (8, 14, 20, 235), (*accent, 140), radius=22, border_width=1)

    fitted_text(draw, (95, CANVAS_H - 298), teaser_title.upper(), font=f_badge, fill=(*accent, 255))
    fitted_text(draw, (95, CANVAS_H - 256), teaser_body, font=f_body, fill=(240, 245, 250, 255), spacing=7)

    draw_footer(draw, next_hint="swipe to discover →")

    final = Image.alpha_composite(canvas, overlay)
    save_slide(final, out_path)


def build_fact_slide(raw_path, out_path, cat, slide_num, fact_label, title, body_text, stat_text, accent, light_accent, crop="center", zoom=1.05):
    canvas = create_base_canvas(raw_path, focus_crop=crop, zoom=zoom)
    overlay = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    draw_header(draw, cat, f"0{slide_num} / 05", accent_color=accent)

    card_box = (60, CANVAS_H - 445, CANVAS_W - 60, CANVAS_H - 95)
    draw_pill(draw, card_box, (8, 14, 20, 235), (*accent, 140), radius=24, border_width=1)

    f_num_w = f_fact_num.getbbox(fact_label)[2]
    pill_fact = (95, CANVAS_H - 415, 95 + f_num_w + 36, CANVAS_H - 375)
    draw_pill(draw, pill_fact, (16, 26, 32, 220), (*accent, 180), radius=14)
    fitted_text(draw, (113, CANVAS_H - 408), fact_label, font=f_fact_num, fill=(*light_accent, 255))

    fitted_text(draw, (95, CANVAS_H - 360), title, font=f_title, fill=(255, 255, 255, 255))
    fitted_text(draw, (95, CANVAS_H - 302), body_text, font=f_body, fill=(220, 232, 238, 250), spacing=7)

    if stat_text:
        stat_w = f_badge.getbbox(stat_text)[2]
        pill_stat = (95, CANVAS_H - 172, 95 + stat_w + 50, CANVAS_H - 124)
        draw_pill(draw, pill_stat, (14, 22, 28, 200), (*accent, 120), radius=14)
        draw.ellipse((112, CANVAS_H - 153, 122, CANVAS_H - 143), fill=accent)
        fitted_text(draw, (134, CANVAS_H - 158), stat_text, font=f_badge, fill=(*light_accent, 255))

    next_hint = "next fact →" if slide_num < 4 else "take action →"
    draw_footer(draw, next_hint=next_hint)

    final = Image.alpha_composite(canvas, overlay)
    save_slide(final, out_path)


def build_slide_5(raw_path, out_path, cat, brand_label, share_topic, cta_subtext, follow_subtext, question_text, accent, light_accent):
    canvas = create_base_canvas(raw_path, focus_crop="center", zoom=1.0)
    scrim = Image.new("RGBA", (CANVAS_W, CANVAS_H), (4, 7, 12, 195))
    canvas = Image.alpha_composite(canvas, scrim)

    overlay = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    draw_header(draw, cat, "05 / 05", accent_color=accent)

    fitted_text(draw, (64, 150), "ENJOYED THIS ANATOMY LESSON?", font=f_headline, fill=(255, 255, 255, 255))
    fitted_text(draw, (64, 220), "Support science education & stay curious.", font=f_subhead, fill=(*light_accent, 255))

    card1 = (60, 310, CANVAS_W - 60, 520)
    draw_pill(draw, card1, (10, 18, 26, 230), (*accent, 160), radius=22, border_width=1)
    fitted_text(draw, (95, 345), f"SHARE WITH SOMEONE WHO LOVES {share_topic.upper()}", font=f_title, fill=(255, 255, 255, 255))
    fitted_text(draw, (95, 415), cta_subtext, font=f_body, fill=(210, 225, 235, 240), spacing=6)

    card2 = (60, 555, CANVAS_W - 60, 765)
    draw_pill(draw, card2, (10, 18, 26, 230), (255, 255, 255, 60), radius=22, border_width=1)
    fitted_text(draw, (95, 590), "FOLLOW @PLANTSCIENCE.BOT FOR DAILY SCIENCE", font=f_title, fill=(*light_accent, 255))
    fitted_text(draw, (95, 660), follow_subtext, font=f_body, fill=(210, 225, 235, 240), spacing=6)

    card3 = (60, 800, CANVAS_W - 60, CANVAS_H - 120)
    draw_pill(draw, card3, (14, 22, 32, 240), (*accent, 200), radius=22, border_width=1)
    fitted_text(draw, (95, 835), "QUESTION FOR THE COMMENTS:", font=f_badge, fill=(*accent, 255))
    fitted_text(draw, (95, 880), question_text, font=f_body, fill=(255, 255, 255, 255), spacing=8)

    draw_footer(draw, next_hint="", show_ai_note=True)

    final = Image.alpha_composite(canvas, overlay)
    save_slide(final, out_path)


# 4 Distinct Human Anatomy Topics
BATCH_CONFIG = [
    {
        "folder": "01-human-eye",
        "category": "Human Optics",
        "accent": (46, 213, 115),       # Emerald
        "light_accent": (140, 245, 180),
        "headline": ["HOW YOUR EYES", "TURN LIGHT INTO VISION"],
        "teaser_title": "Biological Camera",
        "teaser_body": "Your cornea and lens focus light on the retina,\nwhere photoreceptors begin signals for vision.",
        "share_topic": "Human Vision & Science",
        "cta_subtext": "Tap the send arrow to share these eye anatomy insights\nwith biology students, doctors, and curious minds.",
        "follow_subtext": "Explore human anatomy, cellular biology, and\nbiomechanics with new posts four days each week.",
        "question": "Why do you think the center of your vision is\nsharper than the edges?",
        "raw_files": [
            "raw_eye_01.png",
            "raw_eye_02.png",
            "raw_eye_03.png",
            "raw_eye_04.png",
            "raw_eye_05.png"
        ],
        "facts": [
            ("FACT 01", "The Dual Refractive Lens", "The cornea provides two-thirds of the eye's total optical\npower (43 diopters), while the flexible crystalline lens fine-tunes\nfocal distance for sharp vision.", "43 Diopters Cornea Focus"),
            ("FACT 02", "120M Rods & 6M Cones", "Rods detect single photons in dim moonlight, while\nspecialized cone photoreceptors decode red, green, and blue\nwavelengths in daylight.", "120M Rods • 6M Cones"),
            ("FACT 03", "The Fovea: Fine Detail", "Densely packed cones in the central fovea support\nsharp vision. Its center has no overlying blood\nvessels to obstruct incoming light.", "Central Vision & Fine Detail")
        ],
        "caption": """Your eye focuses light, and your retina begins converting it into neural signals.

Inside the human eye:
1. The cornea supplies most of the eye's focusing power; the lens adjusts focus for different distances.
2. Over 120 million rods detect dim light, while 6 million cones decode vibrant color.
3. Densely packed cones in the central fovea support sharp central vision.

Why is the center of your vision sharper than the edges?

#humananatomy #vision #optometry #biology #humaneye

AI illustration"""
    },
    {
        "folder": "02-human-heart",
        "category": "Cardiovascular",
        "accent": (255, 75, 75),        # Crimson Red
        "light_accent": (255, 170, 170),
        "headline": ["THE UNSTOPPABLE HYDRAULIC", "PUMP IN YOUR CHEST"],
        "teaser_title": "Biomechanics",
        "teaser_body": "Beating over 100,000 times every day to pump\n2,000 gallons of oxygenated blood through 60,000 miles of vessels.",
        "share_topic": "Cardiovascular Health",
        "cta_subtext": "Send this to someone who loves fitness, physiology,\nor marvels at the mechanics of the human heart.",
        "follow_subtext": "Follow for deep-dive infographics exploring the marvelous\nengineering of human organs and biological systems.",
        "question": "If your heart beats ~100,000 times daily, what healthy\nhabit do you do to protect your cardiovascular system?",
        "raw_files": [
            "raw_heart_01.png",
            "raw_heart_02.png",
            "raw_heart_03.png",
            "raw_heart_04.png",
            "raw_heart_05.png"
        ],
        "facts": [
            ("FACT 01", "The Bioelectric Pacemaker", "The sinoatrial (SA) node generates spontaneous electrical\naction potentials without nervous system cues, firing 60 to\n100 rhythmic pulses every minute.", "60–100 BPM Bioelectric Spark"),
            ("FACT 02", "Four One-Way Valves", "Pressure differences open and close four heart valves.\nThey keep blood moving forward; valve closure\ncontributes to the familiar heart sounds.", "One-Way Blood Flow"),
            ("FACT 03", "Dedicated Fuel Network", "Left and right coronary arteries supply dense capillaries,\ndelivering 5% of all cardiac output directly to sustain the\ncontinuously working myocardium.", "250 ml/min Myocardial Supply")
        ],
        "caption": """Your heart beats 100,000 times a day and pumps 2,000 gallons of blood without taking a single vacation.

How cardiac mechanics work:
1. The sinoatrial node fires spontaneous bioelectric pulses to pace your rhythm autonomously.
2. Four valves open and close with pressure differences to prevent backflow.
3. Dedicated coronary arteries deliver 250 ml/min of oxygenated blood to working muscle.

Did you know your blood vessels would wrap around the Earth more than twice if laid end to end?

#cardiology #humanheart #anatomy #physiology #hearthealth

AI illustration"""
    },
    {
        "folder": "03-human-brain",
        "category": "Neuroscience",
        "accent": (147, 112, 219),      # Electric Purple
        "light_accent": (210, 185, 255),
        "headline": ["THE 86-BILLION-NEURON", "BIOELECTRIC SUPERCOMPUTER"],
        "teaser_title": "Neural Connectome",
        "teaser_body": "Weighing just 3 pounds, your brain consumes 20% of\nyour body's daily energy to process thought, sensation, and memory.",
        "share_topic": "Neuroscience & Psychology",
        "cta_subtext": "Share this with a student, psychology enthusiast, or\nanyone fascinated by the mysteries of human consciousness.",
        "follow_subtext": "Follow for daily visual guides into neuroanatomy, cellular\npathways, and the human biomechanical architecture.",
        "question": "Did you know information travels down myelinated axons\nfaster than a Formula 1 race car (up to 120 m/s)?",
        "raw_files": [
            "raw_brain_01.png",
            "raw_brain_02.png",
            "raw_brain_03.png",
            "raw_brain_04.png",
            "raw_brain_05.png"
        ],
        "facts": [
            ("FACT 01", "Saltatory Action Potentials", "Myelin sheaths formed by oligodendrocytes insulate axons,\nenabling electrical action potentials to jump between Ranvier\nnodes at blistering speeds of 120 m/s.", "120 m/s Nerve Conduction"),
            ("FACT 02", "Signals Across a Tiny Gap", "Vesicles fuse with the presynaptic membrane. Released\nneurotransmitters cross the synaptic cleft and bind\nto receptors on the receiving cell.", "Chemical Synaptic Transmission"),
            ("FACT 03", "The Molecular Fortress", "Astrocyte end-feet and endothelial tight junctions shield\n400 miles of brain microvessels, strictly barring pathogens\nwhile selectively shuttling glucose.", "400 Miles of Capillaries")
        ],
        "caption": """Weighing just 3 pounds, your brain houses 86 billion neurons and 100 trillion synaptic connections.

Inside the human brain:
1. Myelinated axons conduct bioelectric pulses at 120 m/s via saltatory conduction.
2. Vesicles release neurotransmitters, which cross synaptic clefts and bind to receptors.
3. The blood-brain barrier shields 400 miles of capillaries, protecting neural circuits.

Did you know your brain generates enough electrical power while awake to illuminate a low-wattage LED?

#neuroscience #brainfacts #neuroanatomy #psychology #biology

AI illustration"""
    },
    {
        "folder": "04-human-lungs",
        "category": "Pulmonology",
        "accent": (0, 180, 240),        # Cyan Blue
        "light_accent": (160, 230, 255),
        "headline": ["THE MICROSCOPIC AIR SACS", "KEEPING YOU BREATHING"],
        "teaser_title": "Respiratory Mechanics",
        "teaser_body": "Trading life-sustaining oxygen across a microscopic\ncellular barrier thinner than a single red blood cell with every breath.",
        "share_topic": "Respiratory Physiology",
        "cta_subtext": "Send this to someone who loves fitness, respiratory\nscience, or marvels at human cellular engineering.",
        "follow_subtext": "Explore respiratory biology and human anatomy\nwith new infographics four days each week.",
        "question": "How does packing many tiny air sacs into your lungs\nhelp exchange oxygen and carbon dioxide?",
        "raw_files": [
            "raw_lungs_01.png",
            "raw_lungs_02.png",
            "raw_lungs_03.png",
            "raw_lungs_04.png",
            "raw_lungs_05.png"
        ],
        "facts": [
            ("FACT 01", "A Vast Exchange Surface", "Hundreds of millions of microscopic alveoli create\na large, folded surface for gas exchange, packed\ncompactly inside your chest.", "Millions of Tiny Air Sacs"),
            ("FACT 02", "Sub-Micron Diffusion Barrier", "The respiratory membrane between alveolar air and capillary\nblood is less than 0.5 micrometers thick, enabling instantaneous\npassive oxygen diffusion into hemoglobin.", "<0.5 µm Blood-Air Barrier"),
            ("FACT 03", "Anti-Collapse Surfactant", "Type II alveolar cells synthesize pulmonary surfactant\n(DPPC lipids), lowering surface tension to prevent air sacs\nfrom collapsing during deep exhalation.", "DPPC Surfactant Shield")
        ],
        "caption": """Right now, 300 million microscopic bubbles in your chest are trading vital gases across a barrier thinner than a cell.

Inside your lungs:
1. Hundreds of millions of alveoli create a large, folded surface for gas exchange.
2. Oxygen diffuses across a membrane less than 0.5 micrometers thick in just a fraction of a second.
3. Specialized pulmonary surfactant prevents delicate air sacs from collapsing as you exhale.

Take a deep breath right now—did you realize your lungs had this much surface area?

#humananatomy #lungs #respiratorysystem #pulmonology #biology

AI illustration"""
    }
]


def render_batch():
    print("=" * 70)
    print("🎨 Running Master Carousel Batch Compositor")
    print(f"📁 Reading from: {RAW_DIR}")
    print(f"📁 Writing to:   {QUEUE_DIR}")
    print("=" * 70)

    source_dir = RAW_DIR

    os.makedirs(QUEUE_DIR, exist_ok=True)

    for post in BATCH_CONFIG:
        post_folder = os.path.join(QUEUE_DIR, post["folder"])
        os.makedirs(post_folder, exist_ok=True)
        print(f"\n▶ Compositing: {post['folder']} ({post['category']})")

        # Map files
        raw_paths = []
        for rf in post["raw_files"]:
            p1 = os.path.join(source_dir, rf)
            # Try alternate naming without 'raw_'
            p2 = os.path.join(source_dir, rf.replace("raw_", ""))
            p_final = p1 if os.path.exists(p1) else (p2 if os.path.exists(p2) else None)
            if not p_final:
                print(f"  [Error] Raw image '{rf}' not found in '{source_dir}'!", file=sys.stderr)
                sys.exit(1)
            raw_paths.append(p_final)

        # Slide 1: Hook
        out_s1 = os.path.join(post_folder, "slide_01.jpg")
        print(f"  Rendering Slide 1: Hook Headline...")
        build_slide_1(
            raw_paths[0],
            out_s1,
            post["category"],
            post["headline"],
            post["teaser_title"],
            post["teaser_body"],
            post["accent"],
            post["light_accent"]
        )

        # Slides 2-4: Facts
        for s_idx, (f_num, f_title, f_body_text, f_stat) in enumerate(post["facts"], start=2):
            out_s = os.path.join(post_folder, f"slide_0{s_idx}.jpg")
            print(f"  Rendering Slide {s_idx}: {f_title}...")
            build_fact_slide(
                raw_paths[s_idx - 1],
                out_s,
                post["category"],
                s_idx,
                f_num,
                f_title,
                f_body_text,
                f_stat,
                post["accent"],
                post["light_accent"]
            )

        # Slide 5: CTA
        out_s5 = os.path.join(post_folder, "slide_05.jpg")
        print(f"  Rendering Slide 5: Call to Action...")
        build_slide_5(
            raw_paths[4],
            out_s5,
            post["category"],
            "@plantscience.bot",
            post["share_topic"],
            post["cta_subtext"],
            post["follow_subtext"],
            post["question"],
            post["accent"],
            post["light_accent"]
        )

        # Caption
        caption_path = os.path.join(post_folder, "caption.txt")
        with open(caption_path, "w", encoding="utf-8") as f:
            f.write(post["caption"].strip() + "\n")
        print(f"  ✓ Saved caption.txt")

    print("\n" + "=" * 70)
    print("✅ All 4 carousels successfully assembled in queue/!")
    print("Double-click preview.html to review before publishing.")
    print("=" * 70)


def main():
    global RAW_DIR, QUEUE_DIR
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Path(RAW_DIR))
    parser.add_argument("--queue-dir", type=Path, default=Path(QUEUE_DIR))
    parser.add_argument("--no-preview", action="store_true")
    args = parser.parse_args()
    RAW_DIR = str(args.raw_dir.resolve())
    destination = args.queue_dir.resolve()
    # Validate the entire input batch before changing any queued content.
    for post in BATCH_CONFIG:
        for name in post["raw_files"]:
            raw = Path(RAW_DIR) / name
            with Image.open(raw) as image:
                image.verify()
            with Image.open(raw) as image:
                if image.width < 1080 or image.height < 1350:
                    raise ValueError(f"Raw image below minimum 1080x1350: {raw}")
        if (Path(REPO_DIR) / "posted" / post["folder"]).exists():
            raise RuntimeError(f"{post['folder']} has already been archived; refusing to queue it again")
    from publication import read_json
    history = read_json(Path(REPO_DIR) / "posted" / "captions.json")
    journal = read_json(Path(REPO_DIR) / "posted" / "publication_state.json")
    if any(post["folder"] in history or post["folder"] in journal for post in BATCH_CONFIG):
        raise RuntimeError("This batch has publication history. Use new post IDs for new content.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".carousel-build-", dir=destination.parent) as staging:
        QUEUE_DIR = staging
        render_batch()
        from post_next import find_queued_posts
        from publication import validate_post
        for post in find_queued_posts(Path(staging)):
            validate_post(post)
        destination.mkdir(parents=True, exist_ok=True)
        backup = Path(REPO_DIR) / ".build-backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        for post in BATCH_CONFIG:
            target = destination / post["folder"]
            if target.exists():
                backup.mkdir(parents=True, exist_ok=True)
                shutil.move(str(target), str(backup / post["folder"]))
            shutil.move(str(Path(staging) / post["folder"]), str(target))
    QUEUE_DIR = str(destination)
    if not args.no_preview:
        subprocess.run(["node", "build_preview.js"], cwd=REPO_DIR, check=True)


if __name__ == "__main__":
    main()
