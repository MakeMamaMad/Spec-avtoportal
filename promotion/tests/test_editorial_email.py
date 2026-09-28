from __future__ import annotations

import unittest

from promotion.send_editorial_email import mark_sent, parse_recipients, pending_email_entries


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


if __name__ == "__main__":
    unittest.main()
