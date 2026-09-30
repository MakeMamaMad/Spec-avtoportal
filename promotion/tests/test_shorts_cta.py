import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from tools.autoposter.src.ai import storyboard  # noqa: E402
from tools.autoposter.src.render import short_v2  # noqa: E402

ITEM = {"title": "Новый полуприцеп", "summary": "Краткое описание новости.", "slug": "x", "url": "https://example.com/a"}


def _raw(narrations):
    return {"scenes": [
        {"id": f"s{i}", "seconds": 6, "overlay": "ТЕКСТ", "narration": n, "visual_prompt": "truck"}
        for i, n in enumerate(narrations, 1)
    ]}


class ShortsCtaTest(unittest.TestCase):
    def test_ai_storyboard_gets_cta_appended(self):
        board = storyboard._validate_ai_storyboard(_raw(["a", "b", "c", "d"]), ITEM)
        self.assertEqual(board.scenes[-1].id, "cta")
        self.assertEqual(len(board.scenes), 5)

    def test_ai_closing_line_replaced(self):
        board = storyboard._validate_ai_storyboard(_raw(["a", "b", "c", "Подробности на сайте"]), ITEM)
        self.assertEqual(board.scenes[-1].id, "cta")
        self.assertEqual(len(board.scenes), 4)
        self.assertIn("Подписывайтесь", board.voiceover)

    def test_last_frame_differs_by_platform(self):
        with tempfile.TemporaryDirectory() as tmp:
            bg = Path(tmp) / "bg.png"
            Image.new("RGB", (1080, 1920), (90, 90, 90)).save(bg)
            scene = storyboard.fallback_storyboard(ITEM).scenes[-1]
            yt = short_v2.render_scene_frame(scene, bg, Path(tmp) / "yt.png", index=5, total=5, format_name="breaking", platform="youtube")
            tt = short_v2.render_scene_frame(scene, bg, Path(tmp) / "tt.png", index=5, total=5, format_name="breaking", platform="tiktok")
            # The CTA card paints a large orange subscribe button on YouTube only.
            def orange(path):
                return sum(1 for px in Image.open(path).convert("RGB").getdata() if px == short_v2.ORANGE)
            self.assertGreater(orange(yt), 40000)
            self.assertLess(orange(tt), 40000)


if __name__ == "__main__":
    unittest.main()
