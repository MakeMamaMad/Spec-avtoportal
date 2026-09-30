import json
import sys
import types
import unittest

# The publisher imports the YouTube/Google client libraries at module level;
# stub them when they are not installed (only link helpers are tested here).
for _name, _attrs in {
    "googleapiclient": {}, "googleapiclient.discovery": {"build": None}, "googleapiclient.http": {"MediaFileUpload": None},
    "google": {}, "google.oauth2": {}, "google.oauth2.credentials": {"Credentials": None},
    "google.auth": {}, "google.auth.transport": {}, "google.auth.transport.requests": {"Request": None},
}.items():
    try:
        __import__(_name)
        continue
    except ImportError:
        pass
    _mod = sys.modules.setdefault(_name, types.ModuleType(_name))
    for _k, _v in _attrs.items():
        if not hasattr(_mod, _k):
            setattr(_mod, _k, _v)

from tools.autoposter.src.ai.storyboard import _url, fallback_storyboard
from tools.autoposter.src.publish.social_v2 import _with_site_link


PUBLIC_ITEM = '{"title": "«Стеллар Мотор Рус» представил на Comtrans новый Foton R 6x2, созданный вместе с российскими ритейлерами", "summary": "Официальный дистрибьютор коммерческой техники Foton в России расширяет линейку крупнотоннажных грузовиков категории N3. Она пополнится новой модификацией — шасси Foton R 6x2полной массой 25 тонн для перевозки грузов с соблюдением...", "domain": "truckmix.ru", "source": "TRUCKMIX — новости спецтехники и грузового транспорта", "published_at": "2026-09-30T09:01:33+00:00", "tags": ["спецтехника", "грузовики", "прицепы", "полуприцепы"], "content": ""}'


class ShortsLinksTest(unittest.TestCase):
    def test_details_link_is_our_article_not_the_source(self):
        item = json.loads(PUBLIC_ITEM)
        item["slug"] = "jac-musorovoz-06501839"
        item["link"] = "https://truckmix.ru/news/x"
        self.assertEqual(_url(item), "https://spec-avtoportal.ru/news/jac-musorovoz-06501839/")
        board = fallback_storyboard(item)
        self.assertNotIn("truckmix.ru", board.youtube_description)
        self.assertIn("spec-avtoportal.ru/news/jac-musorovoz-06501839/", board.youtube_description)

    def test_news_without_site_page_links_home(self):
        item = {"title": "Коротко", "slug": "thin-news-1", "link": "https://truckmix.ru/news/x"}
        self.assertEqual(_url(item), "https://spec-avtoportal.ru/")

    def test_links_get_platform_utm(self):
        text = _with_site_link("Подробности: https://spec-avtoportal.ru/news/a/", "tiktok")
        self.assertIn("https://spec-avtoportal.ru/news/a/?utm_source=tiktok&utm_medium=video&utm_campaign=shorts", text)
        self.assertNotIn("Подробнее на сайте", text)

    def test_site_link_added_when_missing(self):
        text = _with_site_link("Новость дня", "youtube")
        self.assertIn("Подробнее на сайте: https://spec-avtoportal.ru/?utm_source=youtube", text)

    def test_existing_utm_kept(self):
        text = _with_site_link("https://spec-avtoportal.ru/?utm_source=x", "youtube")
        self.assertEqual(text.count("utm_source"), 1)


if __name__ == "__main__":
    unittest.main()
