from __future__ import annotations

import unittest
from datetime import datetime, timezone

from tools.social_schedule_watchdog import due_actions


class SocialScheduleWatchdogTests(unittest.TestCase):
    def test_recovers_missed_morning_news_and_digests(self) -> None:
        now = datetime(2026, 9, 25, 7, 0, tzinfo=timezone.utc)
        actions = due_actions(
            now,
            {"updated_at": "2026-09-25T03:05:00+00:00"},
            {"digests": {}},
            {"digests": {}},
        )
        self.assertIn("news", actions)
        self.assertIn("telegram_am", actions)
        self.assertIn("vk_am", actions)

    def test_does_not_repeat_completed_jobs(self) -> None:
        now = datetime(2026, 9, 25, 7, 0, tzinfo=timezone.utc)
        actions = due_actions(
            now,
            {"updated_at": "2026-09-25T06:15:00+00:00"},
            {"digests": {"2026-09-25:am": {"message_id": 1}}},
            {"digests": {"2026-09-25:am": {"post_id": 1}}},
        )
        self.assertEqual(actions, [])

    def test_evening_recovery_uses_pm_keys(self) -> None:
        now = datetime(2026, 9, 25, 17, 0, tzinfo=timezone.utc)
        actions = due_actions(
            now,
            {"updated_at": "2026-09-25T15:10:00+00:00"},
            {"digests": {"2026-09-25:am": {}}},
            {"digests": {"2026-09-25:am": {}}},
        )
        self.assertIn("telegram_pm", actions)
        self.assertIn("vk_pm", actions)
        self.assertNotIn("telegram_am", actions)
        self.assertNotIn("vk_am", actions)


if __name__ == "__main__":
    unittest.main()
