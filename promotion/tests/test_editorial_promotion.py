from __future__ import annotations

import unittest
from datetime import datetime, timezone

from promotion.build_editorial_promo import article_body, pick_action, used_pairs


class EditorialPlannerTests(unittest.TestCase):
    def test_mexzona_is_preferred_as_proven_automatic_target(self) -> None:
        articles = [
            {
                "slug": "service",
                "title": "Техническое обслуживание полуприцепа",
                "description": "Практический материал",
                "lead": "Проверяем узлы и интервалы.",
                "sections": [],
            }
        ]
        targets = [
            {
                "id": "truckmix-publishing",
                "name": "TRUCKmix",
                "platform": "publisher",
                "status": "priority_candidate",
                "audience_hint": "грузовая техника",
            },
            {
                "id": "mexzona",
                "name": "MEXZONA",
                "platform": "publisher",
                "status": "candidate",
                "audience_hint": "спецтехника грузовая техника",
            },
        ]

        action = pick_action(
            articles,
            targets,
            [],
            datetime(2026, 9, 24, 10, 0, tzinfo=timezone.utc),
        )

        self.assertIsNotNone(action)
        self.assertEqual(action["target_id"], "mexzona")
        self.assertEqual(action["execution"], "automatic")
        self.assertEqual(action["status"], "ready_for_publish")

    def test_recent_target_is_in_cooldown(self) -> None:
        articles = [{"slug": "service", "title": "ТО", "sections": []}]
        targets = [
            {
                "id": "mexzona",
                "name": "MEXZONA",
                "platform": "publisher",
                "status": "candidate",
            },
            {
                "id": "mashport",
                "name": "МашПорт",
                "platform": "publisher",
                "status": "candidate",
            },
        ]
        history = [
            {
                "target_id": "mexzona",
                "slug": "old",
                "created_at": "2026-09-23T10:00:00+00:00",
                "status": "submitted",
            }
        ]

        action = pick_action(
            articles,
            targets,
            history,
            datetime(2026, 9, 24, 10, 0, tzinfo=timezone.utc),
        )

        self.assertIsNone(action)

        manual_action = pick_action(
            articles,
            targets,
            history,
            datetime(2026, 9, 24, 10, 0, tzinfo=timezone.utc),
            allow_manual=True,
        )
        self.assertIsNotNone(manual_action)
        self.assertEqual(manual_action["target_id"], "mashport")
        self.assertEqual(manual_action["execution"], "manual")


    def test_email_target_is_planned_without_manual_flag(self) -> None:
        articles = [
            {
                "slug": "nagruzka-na-os",
                "title": "Нагрузка на ось: как проверить автопоезд перед рейсом",
                "lead": "Практический материал для перевозчиков.",
                "sections": [],
            }
        ]
        targets = [
            {
                "id": "com-stil-editorial",
                "name": "COM-STIL",
                "platform": "publisher",
                "status": "priority_candidate",
                "automation": "email_submission",
                "contact": "info@example.com",
                "audience_hint": "перевозчики грузоперевозки",
            }
        ]

        action = pick_action(
            articles,
            targets,
            [],
            datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc),
        )

        self.assertIsNotNone(action)
        self.assertEqual(action["execution"], "email")
        self.assertEqual(action["status"], "ready_for_email")
        self.assertIn("Материал для COM-STIL", action["email_subject"])
        self.assertIn("utm_source=com-stil-editorial", action["site_url"])
        self.assertIn(action["site_url"], action["email_body"])

    def test_legacy_knowledge_item_key_blocks_duplicate(self) -> None:
        pairs = used_pairs(
            [
                {
                    "target_id": "mexzona",
                    "item_key": "knowledge:nagruzka-na-os",
                    "status": "verified_in_author_cabinet",
                }
            ]
        )
        self.assertIn(("mexzona", "nagruzka-na-os"), pairs)


    def test_article_body_uses_original_knowledge_content(self) -> None:
        body = article_body(
            {
                "title": "Тест",
                "lead": "Вводная.",
                "sections": [
                    {"heading": "Проверка", "bullets": ["Первый пункт"]},
                ],
            },
            "https://spec-avtoportal.ru/knowledge/test/",
        )
        self.assertIn("Тест", body)
        self.assertIn("• Первый пункт", body)
        self.assertIn("Источник и полная версия:", body)


if __name__ == "__main__":
    unittest.main()
