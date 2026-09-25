from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from tools.video_schedule_watchdog import due_slot

MSK = ZoneInfo("Europe/Moscow")


class VideoScheduleWatchdogTests(unittest.TestCase):
    def test_morning_slot_is_due_after_target_time(self) -> None:
        state = {"days": {}}
        self.assertEqual(
            due_slot(datetime(2026, 9, 25, 10, 52, tzinfo=MSK), state),
            "am",
        )

    def test_morning_slot_is_not_due_before_window(self) -> None:
        state = {"days": {}}
        self.assertEqual(
            due_slot(datetime(2026, 9, 25, 10, 20, tzinfo=MSK), state),
            "",
        )

    def test_published_morning_slot_is_not_repeated(self) -> None:
        state = {"days": {"2026-09-25": {"am": "published"}}}
        self.assertEqual(
            due_slot(datetime(2026, 9, 25, 11, 30, tzinfo=MSK), state),
            "",
        )

    def test_evening_slot_is_due_after_target_time(self) -> None:
        state = {"days": {"2026-09-25": {"am": "published"}}}
        self.assertEqual(
            due_slot(datetime(2026, 9, 25, 18, 40, tzinfo=MSK), state),
            "pm",
        )

    def test_evening_slot_does_not_repeat(self) -> None:
        state = {"days": {"2026-09-25": {"am": "published", "pm": "published"}}}
        self.assertEqual(
            due_slot(datetime(2026, 9, 25, 20, 0, tzinfo=MSK), state),
            "",
        )


if __name__ == "__main__":
    unittest.main()
