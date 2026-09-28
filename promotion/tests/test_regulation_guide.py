from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import build_seo  # noqa: E402

BASE = {
    "slug": "test-doc",
    "code": "Приказ № 1",
    "title": "Тестовый документ",
    "type": "Приказ",
    "status": "Действует",
    "official_url": "https://example.org/doc",
}


def ld_blocks(page: str) -> list[dict]:
    return [json.loads(m) for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page)]


class RegulationGuideTests(unittest.TestCase):
    def test_page_without_guide_has_no_faq_markup(self) -> None:
        page = build_seo.render_regulation_page(dict(BASE), "2026-09-28", {"items": []})
        self.assertEqual([b["@type"] for b in ld_blocks(page)], ["WebPage"])
        self.assertIn("<title>Приказ № 1 — Тестовый документ | СпецАвтоПортал</title>", page)

    def test_guide_renders_sections_faq_and_sources(self) -> None:
        item = dict(BASE)
        item["guide"] = {
            "seo_title": "Приказ № 1: разбор",
            "description": "Короткое описание <для> поиска",
            "lead": "Вступление",
            "sections": [{"heading": "Раздел", "bullets": ["пункт <b>"], "numbered": ["шаг"]}],
            "faq": [{"q": "Действует?", "a": "Да."}, {"q": "", "a": "пропуск"}],
            "sources": [{"label": "Портал", "url": "https://example.org/doc"}, {"label": "bad", "url": "javascript:x"}],
        }
        page = build_seo.render_regulation_page(item, "2026-09-28", {"items": []})
        self.assertIn("<title>Приказ № 1: разбор | СпецАвтоПортал</title>", page)
        self.assertIn('content="Короткое описание &lt;для&gt; поиска"', page)
        self.assertIn("<h2>Раздел</h2>", page)
        self.assertIn("<li>пункт &lt;b&gt;</li>", page)
        self.assertIn("<summary>Действует?</summary>", page)
        self.assertNotIn("javascript:x", page)
        faq = [b for b in ld_blocks(page) if b["@type"] == "FAQPage"]
        self.assertEqual(len(faq), 1)
        self.assertEqual(len(faq[0]["mainEntity"]), 1)
        self.assertEqual(faq[0]["mainEntity"][0]["acceptedAnswer"]["text"], "Да.")

    def test_every_guide_is_well_formed(self) -> None:
        data = json.loads((ROOT / "frontend/data/regulations.json").read_text("utf-8"))
        guides = [x for x in data["items"] if x.get("guide")]
        self.assertGreaterEqual(len(guides), 2)
        for item in guides:
            guide = item["guide"]
            self.assertTrue(item["official_url"].startswith("https://"), item["slug"])
            self.assertLessEqual(len(guide["description"]), 200, item["slug"])
            self.assertTrue(guide["sections"], item["slug"])
            for row in guide.get("faq", []):
                self.assertTrue(row["q"] and row["a"], item["slug"])
            for source in guide.get("sources", []):
                self.assertTrue(source["url"].startswith("https://"), item["slug"])

    def test_order_212_has_guide(self) -> None:
        data = json.loads((ROOT / "frontend/data/regulations.json").read_text("utf-8"))
        item = next(x for x in data["items"] if x["slug"] == "mintrans-212-2026")
        guide = item["guide"]
        self.assertGreaterEqual(len(guide["sections"]), 6)
        self.assertGreaterEqual(len(guide["faq"]), 3)
        self.assertLessEqual(len(guide["description"]), 200)
        for source in guide["sources"]:
            self.assertTrue(source["url"].startswith("https://"))


if __name__ == "__main__":
    unittest.main()
