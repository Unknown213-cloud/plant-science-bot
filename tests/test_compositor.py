import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
import build_carousel_batch as compositor


class CompositorTests(unittest.TestCase):
    def test_missing_input_leaves_existing_queue_untouched(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            queue = root / "queue"
            queue.mkdir()
            marker = queue / "existing.txt"
            marker.write_text("keep")
            with patch("sys.argv", ["builder", "--raw-dir", str(root / "missing"),
                                     "--queue-dir", str(queue), "--no-preview"]):
                with self.assertRaises(FileNotFoundError):
                    compositor.main()
            self.assertEqual(marker.read_text(), "keep")

    def test_long_cta_heading_fits_inside_card(self):
        draw = type("Recorder", (), {"text": lambda self, xy, text, **kw: setattr(self, "font", kw["font"])})()
        for post in compositor.BATCH_CONFIG:
            text = f"SHARE WITH SOMEONE WHO LOVES {post['share_topic'].upper()}"
            compositor.fitted_text(draw, (95, 345), text, compositor.f_title, "white")
            self.assertLessEqual(draw.font.getlength(text), 890)
            self.assertGreaterEqual(draw.font.size, 18)

    def test_slide_save_is_real_rgb_jpeg(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "slide.jpg"
            compositor.save_slide(Image.new("RGBA", (1080, 1350)), output)
            with Image.open(output) as image:
                self.assertEqual((image.format, image.mode, image.size), ("JPEG", "RGB", (1080, 1350)))

    def test_slide_counter_keeps_header_margin(self):
        draw = type("Recorder", (), {"text": lambda self, xy, text, **kw: None})()
        compositor.fitted_text(draw, (920, 63), "01 / 05", compositor.f_badge, "white")
