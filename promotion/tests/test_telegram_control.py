from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import telegram_control


class TelegramControlTests(unittest.TestCase):
    def test_explicit_chat_id_wins(self) -> None:
        with patch.dict(os.environ, {"REPORT_TELEGRAM_CHAT_ID": "-100123"}, clear=False):
            self.assertEqual(
                telegram_control.resolve_control_chat_id("token"),
                "-100123",
            )

    def test_discovers_control_channel_when_secret_is_empty(self) -> None:
        calls = []

        def fake_call(token: str, method: str, payload=None):
            calls.append(method)
            if method == "getWebhookInfo":
                return {"url": ""}
            if method == "getUpdates":
                return [
                    {
                        "update_id": 10,
                        "channel_post": {
                            "chat": {
                                "id": -100111,
                                "type": "channel",
                                "title": "Новости",
                            }
                        },
                    },
                    {
                        "update_id": 20,
                        "my_chat_member": {
                            "chat": {
                                "id": -100222,
                                "type": "channel",
                                "title": "SpecAvto Control",
                            }
                        },
                    },
                ]
            raise AssertionError(method)

        with patch.dict(os.environ, {"REPORT_TELEGRAM_CHAT_ID": ""}, clear=False):
            with patch.object(telegram_control, "telegram_call", side_effect=fake_call):
                chat_id = telegram_control.resolve_control_chat_id("token")

        self.assertEqual(chat_id, "-100222")
        self.assertEqual(calls, ["getWebhookInfo", "getUpdates"])

    def test_missing_channel_is_error_not_silent_success(self) -> None:
        def fake_call(token: str, method: str, payload=None):
            if method == "getWebhookInfo":
                return {"url": ""}
            if method == "getUpdates":
                return []
            raise AssertionError(method)

        with patch.dict(os.environ, {"REPORT_TELEGRAM_CHAT_ID": ""}, clear=False):
            with patch.object(telegram_control, "telegram_call", side_effect=fake_call):
                with self.assertRaises(RuntimeError):
                    telegram_control.resolve_control_chat_id("token")


if __name__ == "__main__":
    unittest.main()
