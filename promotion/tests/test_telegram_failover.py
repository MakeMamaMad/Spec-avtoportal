from __future__ import annotations

import unittest

from promotion.core.telegram_failover import (
    BOT_UNSUPPORTED_STATUS,
    build_manual_action,
    human_contact,
    migrate_legacy_failures,
    unsupported_target_ids,
)


class ContactTests(unittest.TestCase):
    def test_separate_human_contact_is_available(self) -> None:
        target = {
            "id": "example",
            "contact": "@HumanAdmin",
            "contact_type": "advertising_contact",
            "bot_contact": "@AdBot",
        }
        self.assertEqual(human_contact(target), "@HumanAdmin")

    def test_bot_only_contact_is_not_manual_contact(self) -> None:
        target = {
            "id": "example",
            "contact": "@AdBot",
            "contact_type": "advertising_bot",
            "bot_contact": "@AdBot",
        }
        self.assertEqual(human_contact(target), "")

    def test_manual_action_contains_ready_message(self) -> None:
        action = build_manual_action(
            {
                "id": "example",
                "name": "Example",
                "contact": "@HumanAdmin",
                "contact_type": "advertising_contact",
                "bot_contact": "@AdBot",
            },
            {
                "tracking_url": "https://spec-avtoportal.ru/?utm_source=example",
                "outreach_pitch": "Здравствуйте! Готовый текст.",
            },
            created_at="2026-09-24T10:00:00+00:00",
        )
        self.assertIsNotNone(action)
        self.assertEqual(action["status"], "ready")
        self.assertEqual(action["contact"], "@HumanAdmin")
        self.assertIn("Готовый текст", action["message"])


class MigrationTests(unittest.TestCase):
    def test_legacy_bot_failure_becomes_terminal_once(self) -> None:
        history = [
            {
                "target_id": "example",
                "target_name": "Example",
                "contact": "@AdBot",
                "tracking_url": "https://spec-avtoportal.ru/?utm_source=example",
                "status": "waiting_bot_to_bot",
                "detail": "Bad Request: USER_BOT_TO_BOT_DISABLED",
            }
        ]
        targets = [
            {
                "id": "example",
                "name": "Example",
                "contact": "@HumanAdmin",
                "contact_type": "advertising_contact",
                "bot_contact": "@AdBot",
            }
        ]
        queue = [
            {
                "target_id": "example",
                "tracking_url": "https://spec-avtoportal.ru/?utm_source=example",
                "outreach_pitch": "Здравствуйте!",
            }
        ]
        manual = []

        result = migrate_legacy_failures(
            history,
            targets,
            queue,
            manual,
            now="2026-09-24T10:00:00+00:00",
        )

        self.assertEqual(result["migrated"], 1)
        self.assertEqual(result["manual_created"], 1)
        self.assertEqual(history[-1]["status"], BOT_UNSUPPORTED_STATUS)
        self.assertEqual(len(manual), 1)
        self.assertIn("example", unsupported_target_ids(history))

        second = migrate_legacy_failures(
            history,
            targets,
            queue,
            manual,
            now="2026-09-24T11:00:00+00:00",
        )
        self.assertEqual(second["migrated"], 0)
        self.assertEqual(len(manual), 1)


if __name__ == "__main__":
    unittest.main()
