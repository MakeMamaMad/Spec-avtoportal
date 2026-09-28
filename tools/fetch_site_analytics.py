#!/usr/bin/env python3
"""Whole-site analytics for the daily Control report.

The UTM report (tools/fetch_promotion_metrika.py) only sees visits that came
through our tagged promotion links. This job answers the broader questions:

* Yandex Metrika: how many people visited the site at all in the last 7 days
  and where they came from (search, direct, social, messengers, links...).
* Yandex Webmaster: how the site looks in Yandex search — pages in the index,
  excluded pages, site problems, search impressions/clicks and top queries.

Each block fails independently: a missing token or API error in one of them is
recorded in its own ``status`` and never breaks the other or the workflow.

Secrets:
  YANDEX_METRIKA_OAUTH_TOKEN   — scope metrika:read (already used for UTM report)
  YANDEX_WEBMASTER_OAUTH_TOKEN — scope webmaster:hostinfo; if not set, the
                                 Metrika token is tried (works when one OAuth
                                 app was granted both scopes).
  YANDEX_WEBMASTER_HOST        — optional, defaults to https://spec-avtoportal.ru
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "frontend/data/promotion/site_analytics.json"
COUNTER_ID = "106240080"
DEFAULT_HOST = "https://spec-avtoportal.ru"
MSK = timezone(timedelta(hours=3))
PERIOD_DAYS = 7
# Webmaster search statistics arrive with a delay of a few days, so the search
# window ends earlier than "today" to avoid comparing half-filled days.
SEARCH_LAG_DAYS = 3
TOP_QUERIES = 10

METRIKA_URL = "https://api-metrika.yandex.net/stat/v1/data"
WEBMASTER_API = "https://api.webmaster.yandex.net/v4"

Fetcher = Callable[[str, str], Any]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def http_get_json(url: str, token: str) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"OAuth {token}",
            "Accept": "application/json",
            "User-Agent": "SpecAvto-Site-Analytics",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def error_detail(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    return f"{type(exc).__name__} {code}" if code else type(exc).__name__


# --------------------------------------------------------------------------
# Metrika: all traffic by source
# --------------------------------------------------------------------------

def metrika_url() -> str:
    params = {
        "ids": COUNTER_ID,
        "dimensions": "ym:s:lastTrafficSource",
        "metrics": "ym:s:visits,ym:s:users,ym:s:bounceRate,ym:s:pageDepth",
        "date1": f"{PERIOD_DAYS - 1}daysAgo",
        "date2": "today",
        "accuracy": "full",
        "limit": "50",
        "sort": "-ym:s:visits",
        "lang": "ru",
    }
    return METRIKA_URL + "?" + urllib.parse.urlencode(params)


def _num(values: list[Any], index: int) -> float:
    try:
        return float(values[index] or 0)
    except (IndexError, TypeError, ValueError):
        return 0.0


def normalize_metrika(payload: dict[str, Any]) -> dict[str, Any]:
    sources: list[dict[str, Any]] = []
    for row in payload.get("data") or []:
        dims = row.get("dimensions") or [{}]
        dim = dims[0] or {}
        metrics = row.get("metrics") or []
        sources.append(
            {
                "id": str(dim.get("id") or ""),
                "name": str(dim.get("name") or "Не определено"),
                "visits": int(round(_num(metrics, 0))),
                "users": int(round(_num(metrics, 1))),
                "bounce_rate": round(_num(metrics, 2), 1),
                "page_depth": round(_num(metrics, 3), 2),
            }
        )
    sources.sort(key=lambda item: (-item["visits"], item["name"]))
    totals = payload.get("totals") or []
    return {
        "visits": int(round(_num(totals, 0))) if totals else sum(s["visits"] for s in sources),
        "users": int(round(_num(totals, 1))) if totals else sum(s["users"] for s in sources),
        "sources": sources,
    }


def fetch_metrika(token: str, fetch: Fetcher = http_get_json) -> dict[str, Any]:
    block: dict[str, Any] = {"status": "ok", "period_days": PERIOD_DAYS}
    if not token:
        block.update(status="missing_token", detail="Нужен секрет YANDEX_METRIKA_OAUTH_TOKEN (metrika:read).")
        return block
    try:
        block.update(normalize_metrika(fetch(metrika_url(), token)))
    except Exception as exc:  # network/API errors must not break the report
        block.update(status="error", detail=f"Метрика: {error_detail(exc)}")
    return block


# --------------------------------------------------------------------------
# Webmaster: index state and search performance
# --------------------------------------------------------------------------

def normalize_host(value: str) -> str:
    value = (value or "").strip().lower().rstrip("/")
    if "://" not in value:
        value = "https://" + value
    parsed = urllib.parse.urlparse(value)
    return f"{parsed.scheme}://{parsed.netloc.removeprefix('www.')}"


def pick_host(hosts: list[dict[str, Any]], wanted: str) -> dict[str, Any] | None:
    target = normalize_host(wanted)
    for host in hosts:
        url = host.get("unicode_host_url") or host.get("ascii_host_url") or ""
        if normalize_host(url) == target:
            return host
    return None


def webmaster_dt(day: date) -> str:
    # Webmaster expects ISO-8601 date-time with an offset.
    return f"{day.isoformat()}T00:00:00.000+0300"


def search_window(today: date) -> tuple[date, date]:
    date_to = today - timedelta(days=SEARCH_LAG_DAYS)
    return date_to - timedelta(days=PERIOD_DAYS - 1), date_to


def history_url(base: str, date_from: date, date_to: date) -> str:
    params = [
        ("query_indicator", "TOTAL_SHOWS"),
        ("query_indicator", "TOTAL_CLICKS"),
        ("date_from", webmaster_dt(date_from)),
        ("date_to", webmaster_dt(date_to)),
    ]
    return f"{base}/search-queries/all/history?" + urllib.parse.urlencode(params)


def popular_url(base: str, date_from: date, date_to: date) -> str:
    params = [
        ("order_by", "TOTAL_SHOWS"),
        ("query_indicator", "TOTAL_SHOWS"),
        ("query_indicator", "TOTAL_CLICKS"),
        ("query_indicator", "AVG_SHOW_POSITION"),
        ("date_from", webmaster_dt(date_from)),
        ("date_to", webmaster_dt(date_to)),
        ("limit", str(TOP_QUERIES)),
    ]
    return f"{base}/search-queries/popular?" + urllib.parse.urlencode(params)


def sum_history(payload: dict[str, Any], indicator: str) -> int:
    points = (payload.get("indicators") or {}).get(indicator) or []
    return int(round(sum(float(p.get("value") or 0) for p in points)))


def normalize_queries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in payload.get("queries") or []:
        ind = item.get("indicators") or {}
        position = ind.get("AVG_SHOW_POSITION")
        rows.append(
            {
                "query": str(item.get("query_text") or ""),
                "shows": int(round(float(ind.get("TOTAL_SHOWS") or 0))),
                "clicks": int(round(float(ind.get("TOTAL_CLICKS") or 0))),
                "position": round(float(position), 1) if position is not None else None,
            }
        )
    rows.sort(key=lambda row: (-row["shows"], -row["clicks"], row["query"]))
    return rows[:TOP_QUERIES]


def fetch_webmaster(
    token: str,
    host: str,
    today: date,
    fetch: Fetcher = http_get_json,
) -> dict[str, Any]:
    block: dict[str, Any] = {"status": "ok", "host": normalize_host(host)}
    if not token:
        block.update(
            status="missing_token",
            detail="Нужен секрет YANDEX_WEBMASTER_OAUTH_TOKEN (webmaster:hostinfo).",
        )
        return block
    try:
        user_id = fetch(f"{WEBMASTER_API}/user", token).get("user_id")
        hosts = fetch(f"{WEBMASTER_API}/user/{user_id}/hosts", token).get("hosts") or []
        found = pick_host(hosts, host)
        if not found:
            block.update(status="host_not_found", detail=f"Сайт {block['host']} не найден в аккаунте Вебмастера.")
            return block
        host_id = urllib.parse.quote(str(found["host_id"]), safe="")
        base = f"{WEBMASTER_API}/user/{user_id}/hosts/{host_id}"

        summary = fetch(f"{base}/summary", token)
        problems = summary.get("site_problems") or {}
        block["index"] = {
            "searchable_pages": int(summary.get("searchable_pages_count") or 0),
            "excluded_pages": int(summary.get("excluded_pages_count") or 0),
            "sqi": int(summary.get("sqi") or 0),
            "problems": {
                "fatal": int(problems.get("FATAL") or 0),
                "critical": int(problems.get("CRITICAL") or 0),
                "possible": int(problems.get("POSSIBLE_PROBLEM") or 0),
                "recommendation": int(problems.get("RECOMMENDATION") or 0),
            },
        }
    except Exception as exc:
        block.update(status="error", detail=f"Вебмастер: {error_detail(exc)}")
        return block

    date_from, date_to = search_window(today)
    block["search"] = {"date_from": date_from.isoformat(), "date_to": date_to.isoformat()}
    try:
        history = fetch(history_url(base, date_from, date_to), token)
        block["search"]["shows"] = sum_history(history, "TOTAL_SHOWS")
        block["search"]["clicks"] = sum_history(history, "TOTAL_CLICKS")
        block["search"]["top_queries"] = normalize_queries(fetch(popular_url(base, date_from, date_to), token))
    except Exception as exc:
        # Index data is still useful even if search statistics are unavailable.
        block["search"]["status"] = "error"
        block["search"]["detail"] = f"Поисковые запросы: {error_detail(exc)}"
    return block


def build_summary(env: dict[str, str], today: date, fetch: Fetcher = http_get_json) -> dict[str, Any]:
    metrika_token = env.get("YANDEX_METRIKA_OAUTH_TOKEN", "").strip()
    webmaster_token = env.get("YANDEX_WEBMASTER_OAUTH_TOKEN", "").strip() or metrika_token
    host = env.get("YANDEX_WEBMASTER_HOST", "").strip() or DEFAULT_HOST
    return {
        "schema": 1,
        "updated_at": utc_now(),
        "counter_id": COUNTER_ID,
        "metrika": fetch_metrika(metrika_token, fetch),
        "webmaster": fetch_webmaster(webmaster_token, host, today, fetch),
    }


def main() -> int:
    summary = build_summary(dict(os.environ), datetime.now(MSK).date())
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    metrika = summary["metrika"]
    webmaster = summary["webmaster"]
    print(
        "SITE_ANALYTICS "
        f"metrika={metrika['status']} visits={metrika.get('visits', 0)} "
        f"webmaster={webmaster['status']} "
        f"indexed={(webmaster.get('index') or {}).get('searchable_pages', 0)} "
        f"clicks={(webmaster.get('search') or {}).get('clicks', 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
