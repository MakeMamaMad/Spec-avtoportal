from __future__ import annotations

import unittest
from datetime import datetime, timezone

from promotion.send_editorial_email import mark_sent, parse_recipients, pending_email_entries
from promotion.run_daily_editorial_email import sent_email_today


class EditorialEmailTests(unittest.TestCase):
    def test_parse_multiple_recipients(self) -> None:
        self.assertEqual(
            parse_recipients("one@example.com; two@example.com,three@example.com"),
            ["one@example.com", "two@example.com", "three@example.com"],
        )

    def test_pending_email_entries_only_ready_email(self) -> None:
        payload = {
            "entries": [
                {"channel": "email", "status": "ready", "created_at": "2026-09-28T01:00:00Z", "action_id": "a"},
                {"channel": "publisher", "status": "ready", "created_at": "2026-09-28T00:00:00Z", "action_id": "b"},
                {"channel": "email", "status": "completed", "created_at": "2026-09-28T00:00:00Z", "action_id": "c"},
            ]
        }
        rows = pending_email_entries(payload)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["action_id"], "a")

    def test_mark_sent_updates_queue_history_and_summary(self) -> None:
        row = {
            "action_id": "editorial:com-stil-editorial:gabarity-i-massy",
            "channel": "email",
            "target_id": "com-stil-editorial",
            "target_name": "COM-STIL",
            "status": "ready",
            "contact": "info@example.com",
        }
        queue = {"entries": [row]}
        history = {
            "entries": [
                {
                    "target_id": "com-stil-editorial",
                    "slug": "gabarity-i-massy",
                    "status": "email_prepared",
                }
            ]
        }
        summary = {"target_name": "COM-STIL", "status": "email_prepared"}

        mark_sent(queue, history, summary, row, "gmail-123")

        self.assertEqual(row["status"], "completed")
        self.assertEqual(row["gmail_message_id"], "gmail-123")
        self.assertEqual(history["entries"][0]["status"], "email_sent")
        self.assertEqual(summary["status"], "email_sent")

    def test_sent_email_today_prevents_second_daily_email(self) -> None:
        history = {
            "entries": [
                {
                    "status": "email_sent",
                    "sent_at": "2026-09-28T07:18:39+00:00",
                }
            ]
        }
        now = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)
        self.assertTrue(sent_email_today(history, now))

    def test_old_email_does_not_block_new_day(self) -> None:
        history = {
            "entries": [
                {
                    "status": "email_sent",
                    "sent_at": "2026-09-27T07:18:39+00:00",
                }
            ]
        }
        now = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)
        self.assertFalse(sent_email_today(history, now))


if __name__ == "__main__":
    unittest.main()
