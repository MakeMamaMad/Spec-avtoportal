from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import build_seo  # noqa: E402

LEAD = (
    "Производитель объединил на одной платформе топливный элемент, систему хранения "
    "водорода, тяговую батарею, электропривод и электронные системы управления."
)


def item(domain: str, **extra):
    base = {
        "slug": "test-news",
        "title": "Dongfeng показал три водородных грузовика",
        "summary": LEAD,
        "link": f"https://{domain}/news/1",
        "domain": domain,
    }
    base.update(extra)
    return base


class NewsIndexingTests(unittest.TestCase):
    def test_russian_source_copy_is_public_but_not_indexable(self) -> None:
        news = item("gruzovoy.ru")
        self.assertTrue(build_seo.is_public_news(news))
        self.assertFalse(build_seo.is_indexable_news(news))
        self.assertEqual(build_seo.news_index_issues(news), ["russian_source_copy"])

    def test_translated_foreign_source_stays_indexable(self) -> None:
        self.assertTrue(build_seo.is_indexable_news(item("www.globaltrailermag.com")))
        self.assertTrue(build_seo.is_indexable_news(item("krone-trailer.com")))

    def test_own_and_partner_news_are_indexable(self) -> None:
        self.assertTrue(build_seo.is_indexable_news(item("spec-avtoportal.ru")))
        self.assertTrue(build_seo.is_indexable_news(item("www.satpricep.by", partner=True)))

    def test_editorial_text_makes_russian_story_indexable(self) -> None:
        short = item("truckmix.ru", editorial_note="Коротко.")
        self.assertFalse(build_seo.is_indexable_news(short))
        long = item("truckmix.ru", editorial_note="Наш комментарий. " * 30)
        self.assertTrue(build_seo.is_indexable_news(long))

    def test_quality_issues_still_hide_news_from_site(self) -> None:
        thin = item("www.globaltrailermag.com", summary="Коротко")
        self.assertFalse(build_seo.is_public_news(thin))
        self.assertFalse(build_seo.is_indexable_news(thin))

    def test_foreign_domains_match_translator(self) -> None:
        sys.path.insert(0, str(ROOT / "aggregator"))
        import translate_news

        self.assertEqual(set(translate_news.DOMAIN_LANG), set(build_seo.FOREIGN_SOURCE_DOMAINS))


if __name__ == "__main__":
    unittest.main()
