import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.autoposter.src.content import sat  # noqa: E402


class SatShortsTest(unittest.TestCase):
    def setUp(self):
        self.config = sat.load_config()

    def test_catalog_is_valid(self):
        ids = [e["id"] for e in self.config["episodes"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(ids), 6)
        for episode in self.config["episodes"]:
            self.assertTrue(episode["url"].startswith("https://satpricep.by/"))
            self.assertTrue(3 <= len(episode["scenes"]) <= 5, episode["id"])
            for scene in episode["scenes"]:
                self.assertLessEqual(len(scene["overlay"]), 40, scene["overlay"])
                self.assertTrue(scene["narration"].strip())

    def test_pick_skips_published_and_stops_when_exhausted(self):
        first, second = self.config["episodes"][:2]
        self.assertEqual(sat.pick_episode(self.config, [])["id"], first["id"])
        self.assertEqual(sat.pick_episode(self.config, ["x", sat.episode_key(first)])["id"], second["id"])
        everything = [sat.episode_key(e) for e in self.config["episodes"]]
        self.assertIsNone(sat.pick_episode(self.config, everything))

    def test_storyboard_is_marked_ad_and_ends_on_partner_card(self):
        episode = self.config["episodes"][0]
        board = sat.build_storyboard(self.config, episode)
        self.assertEqual(board.format, "partner")
        self.assertEqual(board.scenes[-1].id, "cta-partner")
        self.assertEqual(board.scenes[-1].overlay, "satpricep.by")
        self.assertIn("Реклама", board.youtube_description)
        self.assertIn("Реклама", board.tiktok_caption)
        self.assertIn("utm_campaign=sat_shorts", board.youtube_description)
        self.assertTrue(all(s.source_image_url for s in board.scenes))


if __name__ == "__main__":
    unittest.main()


class SatPhotosTest(unittest.TestCase):
    def test_photo_choice(self):
        config = {"default_photo": "D", "episodes": []}
        manifest = {"u1": ["a1", "a2"], "u2": ["b1"]}
        self.assertEqual(sat.episode_photos(config, {"url": "u1"}, manifest), ["a1", "a2"])
        self.assertEqual(sat.episode_photos(config, {"url": "home"}, manifest), ["a1", "b1"])
        self.assertEqual(sat.episode_photos(config, {"url": "u1", "photos": ["x"]}, manifest), ["x"])
        self.assertEqual(sat.episode_photos(config, {"url": "u1"}, {}), ["D"])

    def test_gallery_parser(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import fetch_sat_photos as f
        html = '<a href="/upload/x/resize_cache/iblock/fb9/940_640_0/abc.webp"><img src="/upload/x/resize_cache/iblock/fb9/220_150_0/abc.webp">'
        self.assertEqual(f.page_images(html, "https://satpricep.by/p/"), ["https://satpricep.by/upload/x/resize_cache/iblock/fb9/940_640_0/abc.webp"])
