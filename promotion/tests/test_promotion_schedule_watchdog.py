from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import tools.promotion_schedule_watchdog as watchdog


class PromotionScheduleWatchdogTests(unittest.TestCase):
    def test_chain_returns_first_missing_step(self) -> None:
        now = datetime(2026, 9, 25, 12, 30, tzinfo=timezone.utc)
        with patch.object(watchdog, "load_json") as load:
            load.side_effect = [
                {"date_moscow": "2026-09-24"},
            ]
            self.assertEqual(watchdog.next_due_action(now), "catalog")

    def test_manual_outreach_is_due_when_ready_task_exists(self) -> None:
        now = datetime(2026, 9, 25, 12, 30, tzinfo=timezone.utc)
        with patch.object(watchdog, "load_json") as load:
            load.side_effect = [
                {"date_moscow": "2026-09-25"},
                {"updated_at": "2026-09-25T09:00:00+00:00"},
                {"updated_at": "2026-09-25T09:40:00+00:00"},
                {"updated_at": "2026-09-25T10:30:00+00:00"},
                {"entries": [{"status": "ready"}]},
                {"date_moscow": "2026-09-24"},
            ]
            self.assertEqual(watchdog.next_due_action(now), "manual_outreach")

    def test_nothing_due_when_all_steps_done(self) -> None:
        now = datetime(2026, 9, 25, 12, 30, tzinfo=timezone.utc)
        with patch.object(watchdog, "load_json") as load:
            load.side_effect = [
                {"date_moscow": "2026-09-25"},
                {"updated_at": "2026-09-25T09:00:00+00:00"},
                {"updated_at": "2026-09-25T09:40:00+00:00"},
                {"updated_at": "2026-09-25T10:30:00+00:00"},
                {"entries": [{"status": "ready"}]},
                {"date_moscow": "2026-09-25"},
            ]
            self.assertEqual(watchdog.next_due_action(now), "")


if __name__ == "__main__":
    unittest.main()
