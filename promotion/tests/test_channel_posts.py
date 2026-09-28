from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from promotion import publish_channel_posts as pcp


class ChannelPostsTests(unittest.TestCase):
    def test_repository_posts_are_valid(self) -> None:
        posts = pcp.load_posts()
        self.assertTrue(posts)
        for post in posts:
            self.assertEqual(pcp.validate(post), [], post["id"])

    def test_only_approved_and_unsent_posts_are_pending(self) -> None:
        posts = [
            {"id": "a", "approved": True, "text_html": "x"},
            {"id": "b", "approved": False, "text_html": "x"},
            {"id": "c", "text_html": "x"},
            {"id": "d", "approved": True, "text_html": "x"},
        ]
        state = {"sent": {"d": {"message_id": 1}}}
        self.assertEqual([p["id"] for p in pcp.pending_posts(posts, state)], ["a"])

    def test_caption_limit_counts_visible_text(self) -> None:
        long_link = '<a href="https://example.org/' + "x" * 2000 + '">ссылка</a>'
        self.assertEqual(pcp.validate({"text_html": long_link}), [])
        post = {"text_html": "я" * 1100, "document": "frontend/files/specavtoportal-chek-list-perevozchika-2026.pdf"}
        self.assertIn("text longer than 1024 characters", pcp.validate(post))

    def test_main_sends_once_and_records_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            posts_dir = Path(tmp) / "posts"
            posts_dir.mkdir()
            (posts_dir / "p1.json").write_text(json.dumps({"id": "p1", "approved": True, "text_html": "<b>Привет</b>", "pin": True}), "utf-8")
            state_path = Path(tmp) / "state.json"
            calls: list[str] = []

            def fake_api(token, method, fields, file_field=None):
                calls.append(method)
                return {"message_id": 42} if method == "sendMessage" else True

            env = {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "@c"}
            with mock.patch.object(pcp, "POSTS_DIR", posts_dir), mock.patch.object(pcp, "STATE_PATH", state_path), \
                    mock.patch.object(pcp, "api_call", side_effect=fake_api), mock.patch.dict("os.environ", env):
                self.assertEqual(pcp.main(), 0)
                self.assertEqual(pcp.main(), 0)
            self.assertEqual(calls, ["sendMessage", "pinChatMessage"])
            state = json.loads(state_path.read_text("utf-8"))
            self.assertEqual(state["sent"]["p1"]["message_id"], 42)
            self.assertTrue(state["sent"]["p1"]["pinned"])
            self.assertEqual(state["sent"]["p1"]["url"], "https://t.me/specavtoportal/42")


if __name__ == "__main__":
    unittest.main()
