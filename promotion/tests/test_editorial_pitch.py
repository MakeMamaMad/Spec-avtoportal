from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from promotion.build_editorial_promo import (
    PITCH_CONFIG_PATH,
    featured_article,
    load_articles,
    pick_action,
)

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)
CONFIG = {
    "active": True,
    "sender_name": "Иван Петров",
    "sender_role": "редактор",
    "featured": {
        "slug": "mintrans-212-2026",
        "kind": "regulation",
        "path": "/regulations/mintrans-212-2026/",
        "title": "Новые правила",
        "pdf_url": "https://spec-avtoportal.ru/files/check.pdf",
        "subject": "Новые правила для перевозчиков",
        "news_hook": "С 1 сентября действуют новые правила.",
        "offer": "Мы подготовили разбор.",
    },
}
KNOWLEDGE = {"items": [{"slug": "gabarity-i-massy", "title": "Габариты", "lead": "Лид"}]}
EMAIL_TARGET = {
    "id": "editor",
    "name": "Журнал",
    "platform": "publisher",
    "automation": "email_submission",
    "contact": "editor@example.com",
    "status": "candidate",
}
AUTO_TARGET = {"id": "mexzona", "name": "MEXZONA", "platform": "publisher", "status": "active"}


class EditorialPitchTests(unittest.TestCase):
    def test_featured_pitch_goes_first_to_email_targets(self) -> None:
        articles = load_articles(KNOWLEDGE, CONFIG)
        action = pick_action(articles, [EMAIL_TARGET], [], NOW, pitch_config=CONFIG)
        self.assertEqual(action["slug"], "mintrans-212-2026")
        self.assertEqual(action["item_key"], "regulation:mintrans-212-2026")
        self.assertIn("/regulations/mintrans-212-2026/?", action["site_url"])
        self.assertIn("utm_source=editor", action["site_url"])
        self.assertEqual(action["email_subject"], "Новые правила для перевозчиков")
        body = action["email_body"]
        self.assertIn("С 1 сентября действуют новые правила.", body)
        self.assertIn("«Журнал»", body)
        self.assertIn("https://spec-avtoportal.ru/files/check.pdf", body)
        self.assertIn(action["site_url"], body)
        self.assertIn("Иван Петров, редактор", body)
        self.assertIn("Отраслевое медиа о грузовой и прицепной технике", body)

    def test_featured_pitch_is_sent_once_then_knowledge_follows(self) -> None:
        articles = load_articles(KNOWLEDGE, CONFIG)
        history = [{"target_id": "editor", "item_key": "regulation:mintrans-212-2026", "status": "email_sent", "created_at": "2026-08-01T00:00:00+00:00"}]
        action = pick_action(articles, [EMAIL_TARGET], history, NOW, pitch_config=CONFIG)
        self.assertEqual(action["slug"], "gabarity-i-massy")
        self.assertIn("/knowledge/gabarity-i-massy/", action["site_url"])

    def test_editor_is_not_emailed_again_within_30_days(self) -> None:
        articles = load_articles(KNOWLEDGE, CONFIG)
        history = [{"target_id": "editor", "item_key": "regulation:mintrans-212-2026", "status": "email_sent", "created_at": "2026-09-10T00:00:00+00:00"}]
        self.assertIsNone(pick_action(articles, [EMAIL_TARGET], history, NOW, pitch_config=CONFIG))

    def test_automatic_publishers_never_get_email_only_pitch(self) -> None:
        articles = load_articles(KNOWLEDGE, CONFIG)
        action = pick_action(articles, [AUTO_TARGET], [], NOW, pitch_config=CONFIG)
        self.assertEqual(action["slug"], "gabarity-i-massy")

    def test_inactive_pitch_and_default_signature(self) -> None:
        self.assertIsNone(featured_article({**CONFIG, "active": False}))
        articles = load_articles(KNOWLEDGE, {})
        action = pick_action(articles, [EMAIL_TARGET], [], NOW, pitch_config={})
        self.assertIn("редакция СпецАвтоПортала", action["email_body"])

    def test_repository_config_is_valid(self) -> None:
        config = json.loads(PITCH_CONFIG_PATH.read_text("utf-8"))
        featured = featured_article(config)
        if featured:
            pdf_url = featured["pitch"].get("pdf_url")
            if pdf_url:
                self.assertTrue(pdf_url.startswith("https://spec-avtoportal.ru/files/"))
            path = featured["path"]
            self.assertTrue(path.startswith(("/regulations/", "/knowledge/")))
            # The pitched page must exist in the site data.
            root = PITCH_CONFIG_PATH.parents[2] / "frontend/data"
            section, slug = path.strip("/").split("/")
            catalog = "regulations.json" if section == "regulations" else "knowledge_articles.json"
            slugs = {x.get("slug") for x in json.loads((root / catalog).read_text("utf-8"))["items"]}
            self.assertIn(slug, slugs)


if __name__ == "__main__":
    unittest.main()
