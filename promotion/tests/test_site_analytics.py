from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import fetch_site_analytics as fsa  # noqa: E402
from send_daily_control_report import site_analytics_lines  # noqa: E402


HOST_ID = "https:spec-avtoportal.ru:443"


def fake_api(responses: dict[str, object]):
    """Return a fetcher that answers by URL substring; unknown URLs raise."""
    calls: list[str] = []

    def fetch(url: str, token: str):
        calls.append(url)
        for needle, value in responses.items():
            if needle in url:
                if isinstance(value, Exception):
                    raise value
                return value
        raise AssertionError(f"unexpected URL {url}")

    fetch.calls = calls  # type: ignore[attr-defined]
    return fetch


WEBMASTER_OK = {
    "/search-queries/all/history": {
        "indicators": {
            "TOTAL_SHOWS": [{"date": "d1", "value": 120}, {"date": "d2", "value": 30.0}],
            "TOTAL_CLICKS": [{"date": "d1", "value": 4}, {"date": "d2", "value": 1}],
        }
    },
    "/search-queries/popular": {
        "queries": [
            {"query_text": "нагрузка на ось", "indicators": {"TOTAL_SHOWS": 40, "TOTAL_CLICKS": 2, "AVG_SHOW_POSITION": 8.26}},
            {"query_text": "габариты автопоезда", "indicators": {"TOTAL_SHOWS": 90, "TOTAL_CLICKS": 3, "AVG_SHOW_POSITION": 12.0}},
        ]
    },
    "/summary": {
        "sqi": 10,
        "searchable_pages_count": 700,
        "excluded_pages_count": 900,
        "site_problems": {"CRITICAL": 1, "POSSIBLE_PROBLEM": 2},
    },
    "/hosts": {
        "hosts": [
            {"host_id": "https:other.ru:443", "ascii_host_url": "https://other.ru/"},
            {"host_id": HOST_ID, "ascii_host_url": "https://spec-avtoportal.ru/"},
        ]
    },
    "/user": {"user_id": 42},
}


class MetrikaTests(unittest.TestCase):
    def test_normalize_uses_totals_and_sorts_sources(self) -> None:
        payload = {
            "data": [
                {"dimensions": [{"id": "direct", "name": "Прямые заходы"}], "metrics": [5, 4, 20, 1.5]},
                {"dimensions": [{"id": "organic", "name": "Переходы из поисковых систем"}], "metrics": [12, 10, 30, 2]},
            ],
            "totals": [17, 13, 26, 1.8],
        }
        result = fsa.normalize_metrika(payload)
        self.assertEqual(result["visits"], 17)
        self.assertEqual(result["users"], 13)
        self.assertEqual([s["id"] for s in result["sources"]], ["organic", "direct"])

    def test_missing_token_is_reported(self) -> None:
        self.assertEqual(fsa.fetch_metrika("")["status"], "missing_token")

    def test_api_error_is_contained(self) -> None:
        err = HTTPError("u", 403, "Forbidden", {}, None)
        block = fsa.fetch_metrika("t", fake_api({"api-metrika": err}))
        self.assertEqual(block["status"], "error")
        self.assertIn("403", block["detail"])


class WebmasterTests(unittest.TestCase):
    def test_full_flow(self) -> None:
        fetch = fake_api(WEBMASTER_OK)
        block = fsa.fetch_webmaster("t", "spec-avtoportal.ru", date(2026, 9, 28), fetch)
        self.assertEqual(block["status"], "ok")
        self.assertEqual(block["index"]["searchable_pages"], 700)
        self.assertEqual(block["index"]["problems"]["critical"], 1)
        self.assertEqual(block["search"]["shows"], 150)
        self.assertEqual(block["search"]["clicks"], 5)
        self.assertEqual(block["search"]["top_queries"][0]["query"], "габариты автопоезда")
        self.assertEqual(block["search"]["top_queries"][1]["position"], 8.3)
        # host_id must be URL-encoded inside the path
        self.assertTrue(any("/hosts/https%3Aspec-avtoportal.ru%3A443/summary" in u for u in fetch.calls))
        # search window ends SEARCH_LAG_DAYS before today and spans PERIOD_DAYS
        self.assertEqual(block["search"]["date_to"], "2026-09-25")
        self.assertEqual(block["search"]["date_from"], "2026-09-19")

    def test_host_matching_ignores_www_and_trailing_slash(self) -> None:
        hosts = [{"host_id": HOST_ID, "unicode_host_url": "https://www.spec-avtoportal.ru/"}]
        self.assertIsNotNone(fsa.pick_host(hosts, "https://spec-avtoportal.ru"))
        self.assertIsNone(fsa.pick_host(hosts, "http://spec-avtoportal.ru"))

    def test_host_not_found(self) -> None:
        responses = dict(WEBMASTER_OK)
        responses["/hosts"] = {"hosts": []}
        block = fsa.fetch_webmaster("t", fsa.DEFAULT_HOST, date(2026, 9, 28), fake_api(responses))
        self.assertEqual(block["status"], "host_not_found")

    def test_search_error_keeps_index_data(self) -> None:
        responses = dict(WEBMASTER_OK)
        responses["/search-queries/all/history"] = RuntimeError("boom")
        block = fsa.fetch_webmaster("t", fsa.DEFAULT_HOST, date(2026, 9, 28), fake_api(responses))
        self.assertEqual(block["status"], "ok")
        self.assertEqual(block["index"]["searchable_pages"], 700)
        self.assertEqual(block["search"]["status"], "error")

    def test_forbidden_gives_scope_hint(self) -> None:
        import io

        body = io.BytesIO(b'{"error_code":"INSUFFICIENT_SCOPE","error_message":"no hostinfo"}')
        err = HTTPError("u", 403, "Forbidden", {}, body)
        block = fsa.fetch_webmaster("t", fsa.DEFAULT_HOST, date(2026, 9, 28), fake_api({"/user": err}))
        self.assertEqual(block["status"], "error")
        self.assertEqual(block["step"], "user")
        self.assertIn("INSUFFICIENT_SCOPE: no hostinfo", block["detail"])
        self.assertIn("webmaster:hostinfo", block["hint"])
        text = "\n".join(site_analytics_lines({"webmaster": block}))
        self.assertIn("внешних ссылках", text)

    def test_token_secret_is_recorded(self) -> None:
        def fetch(url: str, token: str):
            raise RuntimeError("stop")

        both = fsa.build_summary(
            {"YANDEX_METRIKA_OAUTH_TOKEN": "m", "YANDEX_WEBMASTER_OAUTH_TOKEN": "w"}, date(2026, 9, 28), fetch
        )
        self.assertEqual(both["webmaster"]["token_secret"], "YANDEX_WEBMASTER_OAUTH_TOKEN")
        only_metrika = fsa.build_summary({"YANDEX_METRIKA_OAUTH_TOKEN": "m"}, date(2026, 9, 28), fetch)
        self.assertEqual(only_metrika["webmaster"]["token_secret"], "YANDEX_METRIKA_OAUTH_TOKEN")

    def test_webmaster_falls_back_to_metrika_token(self) -> None:
        seen: list[str] = []

        def fetch(url: str, token: str):
            seen.append(token)
            raise RuntimeError("stop")

        summary = fsa.build_summary({"YANDEX_METRIKA_OAUTH_TOKEN": "m"}, date(2026, 9, 28), fetch)
        self.assertEqual(summary["webmaster"]["status"], "error")
        self.assertTrue(seen and all(t == "m" for t in seen))


class ReportLinesTests(unittest.TestCase):
    def test_ok_report(self) -> None:
        webmaster = fsa.fetch_webmaster("t", fsa.DEFAULT_HOST, date(2026, 9, 28), fake_api(WEBMASTER_OK))
        summary = {
            "metrika": {
                "status": "ok",
                "visits": 17,
                "users": 13,
                "sources": [{"name": "Переходы из поисковых систем", "visits": 12}],
            },
            "webmaster": webmaster,
        }
        text = "\n".join(site_analytics_lines(summary))
        self.assertIn("Всего визитов — 17", text)
        self.assertIn("В поиске страниц — 700", text)
        self.assertIn("Серьёзных проблем", text)
        self.assertIn("Показы — 150, клики — 5", text)
        self.assertIn("«габариты автопоезда»", text)

    def test_empty_summary_does_not_crash(self) -> None:
        text = "\n".join(site_analytics_lines({}))
        self.assertIn("ещё не выполнялся", text)


if __name__ == "__main__":
    unittest.main()
