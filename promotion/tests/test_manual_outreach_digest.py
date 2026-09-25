from __future__ import annotations

import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "manual_digest",
    ROOT / "tools/send_manual_outreach_digest.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ManualOutreachDigestTests(unittest.TestCase):
    def test_ready_task_contains_contact_and_message(self) -> None:
        payload = {
            "entries": [
                {
                    "target_name": "Площадка",
                    "contact": "@admin",
                    "status": "ready",
                    "reason": "Нужно написать вручную.",
                    "message": "Здравствуйте! Тестовое сообщение.",
                    "created_at": "2026-09-24T10:00:00+00:00",
                }
            ]
        }

        messages = MODULE.build_messages(payload)

        joined = "\n".join(messages)
        self.assertIn("Кому написать: @admin", joined)
        self.assertIn("Текст сообщения:", joined)
        self.assertIn("Здравствуйте! Тестовое сообщение.", joined)

    def test_completed_task_is_not_sent(self) -> None:
        payload = {
            "entries": [
                {
                    "target_name": "Площадка",
                    "contact": "@admin",
                    "status": "completed",
                    "message": "Не показывать.",
                }
            ]
        }

        messages = MODULE.build_messages(payload)

        self.assertEqual(len(messages), 1)
        self.assertIn("никому писать не нужно", messages[0].lower())
        self.assertNotIn("@admin", messages[0])

    def test_new_manual_task_is_sent_immediately(self) -> None:
        payload = {
            "entries": [
                {
                    "action_id": "task:new",
                    "target_name": "Площадка",
                    "status": "ready",
                }
            ]
        }
        state = {
            "date_moscow": "2026-09-25",
            "action_ids": ["task:old"],
        }
        now = datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)

        self.assertTrue(MODULE.should_send(payload, state, now))

    def test_same_task_is_not_repeated_before_daily_reminder(self) -> None:
        payload = {
            "entries": [
                {
                    "action_id": "task:1",
                    "target_name": "Площадка",
                    "status": "ready",
                }
            ]
        }
        state = {
            "date_moscow": "2026-09-24",
            "action_ids": ["task:1"],
        }
        now = datetime(2026, 9, 25, 8, 0, tzinfo=timezone.utc)

        self.assertFalse(MODULE.should_send(payload, state, now))

    def test_same_task_is_reminded_after_14_moscow_next_day(self) -> None:
        payload = {
            "entries": [
                {
                    "action_id": "task:1",
                    "target_name": "Площадка",
                    "status": "ready",
                }
            ]
        }
        state = {
            "date_moscow": "2026-09-24",
            "action_ids": ["task:1"],
        }
        now = datetime(2026, 9, 25, 11, 5, tzinfo=timezone.utc)

        self.assertTrue(MODULE.should_send(payload, state, now))


if __name__ == "__main__":
    unittest.main()
