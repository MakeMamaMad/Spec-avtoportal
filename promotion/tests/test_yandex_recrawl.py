import json
import sys
import unittest
import urllib.error
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "promotion"))
import yandex_recrawl as rc  # noqa: E402


class FakeApi:
    def __init__(self, remainder):
        self.remainder = remainder
        self.posted = []
        self.sitemaps = []

    def __call__(self, method, url, token, body):
        if url.endswith("/user"):
            return {"user_id": 7}
        if url.endswith("/hosts"):
            return {"hosts": [{"host_id": "https:spec-avtoportal.ru:443", "ascii_host_url": "https://spec-avtoportal.ru/"}]}
        if url.endswith("/recrawl/quota"):
            return {"daily_quota": 20, "quota_remainder": self.remainder}
        if url.endswith("/user-added-sitemaps"):
            if method == "POST":
                self.sitemaps.append(body["url"])
                return {"sitemap_id": "x"}
            return {"sitemaps": [{"sitemap_url": u} for u in self.sitemaps]}
        if url.endswith("/recrawl/queue"):
            self.posted.append(body["url"])
            return {"task_id": f"t{len(self.posted)}"}
        raise AssertionError(url)


class RecrawlTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        tmp = Path(self.tmp.name)
        self.urls = tmp / "urls.txt"
        self.urls.write_text("# comment\nhttps://spec-avtoportal.ru/a/\nhttps://evil.example/x\nhttps://spec-avtoportal.ru/b/\nhttps://spec-avtoportal.ru/a/\n")
        self.state = tmp / "state.json"
        self.patches = [mock.patch.object(rc, "URLS_PATH", self.urls), mock.patch.object(rc, "STATE_PATH", self.state)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_only_own_site_urls_deduplicated(self):
        self.assertEqual(rc.load_urls(self.urls), ["https://spec-avtoportal.ru/a/", "https://spec-avtoportal.ru/b/"])

    def test_respects_quota_and_sends_each_url_once(self):
        api = FakeApi(remainder=1)
        state = rc.run("t", api)
        self.assertEqual(api.posted, ["https://spec-avtoportal.ru/a/"])
        self.assertEqual(state["last_run"]["left"], 1)
        self.state.write_text(json.dumps(state))
        api2 = FakeApi(remainder=5)
        state = rc.run("t", api2)
        self.assertEqual(api2.posted, ["https://spec-avtoportal.ru/b/"])
        self.assertEqual(state["last_run"]["left"], 0)

    def test_nothing_pending_sends_no_urls(self):
        self.state.write_text(json.dumps({"schema": 1, "submitted": {u: {} for u in rc.load_urls(self.urls)}}))
        api = FakeApi(remainder=5)
        rc.run("t", api)
        self.assertEqual(api.posted, [])

    def test_sitemaps_added_once(self):
        api = FakeApi(remainder=0)
        state = rc.run("t", api)
        self.assertEqual(state["last_run"]["sitemaps_added"], rc.SITEMAPS)
        state = rc.run("t", api)
        self.assertEqual(state["last_run"]["sitemaps_added"], [])


if __name__ == "__main__":
    unittest.main()
