#!/usr/bin/env python3
"""Detailed traffic breakdown from Yandex Metrika (read-only).

Writes frontend/data/promotion/traffic_breakdown.json with, for the last 7 and
30 days: sources in detail (search engine / social network / referring site),
landing pages, cities, devices, browsers, new vs returning visitors, a daily
series, and the same cuts for direct visits only — so direct traffic can be
understood instead of written off.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend/data/promotion/traffic_breakdown.json"
COUNTER_ID = "106240080"
API = "https://api-metrika.yandex.net/stat/v1/data"
METRICS = "ym:s:visits,ym:s:users,ym:s:bounceRate,ym:s:pageDepth,ym:s:avgVisitDurationSeconds"
DIRECT = "ym:s:lastTrafficSource=='direct'"

CUTS: dict[str, dict[str, Any]] = {
    "sources": {"dimensions": "ym:s:lastTrafficSource,ym:s:lastSourceEngine", "limit": 40},
    "referrers": {"dimensions": "ym:s:lastReferalSource", "limit": 25, "filters": "ym:s:lastTrafficSource=='referral'"},
    "social": {"dimensions": "ym:s:lastSocialNetwork", "limit": 20, "filters": "ym:s:lastTrafficSource=='social'"},
    "search_phrases": {"dimensions": "ym:s:lastSearchPhrase", "limit": 25, "filters": "ym:s:lastTrafficSource=='organic'"},
    "landing": {"dimensions": "ym:s:startURLPath", "limit": 30},
    "cities": {"dimensions": "ym:s:regionCountry,ym:s:regionCity", "limit": 25},
    "devices": {"dimensions": "ym:s:deviceCategory", "limit": 10},
    "browsers": {"dimensions": "ym:s:browser", "limit": 15},
    "new_vs_returning": {"dimensions": "ym:s:isNewUser", "limit": 5},
    "direct_landing": {"dimensions": "ym:s:startURLPath", "limit": 25, "filters": DIRECT},
    "direct_cities": {"dimensions": "ym:s:regionCountry,ym:s:regionCity", "limit": 20, "filters": DIRECT},
    "direct_browsers": {"dimensions": "ym:s:browser", "limit": 15, "filters": DIRECT},
    "direct_devices": {"dimensions": "ym:s:deviceCategory", "limit": 10, "filters": DIRECT},
    "direct_new_vs_returning": {"dimensions": "ym:s:isNewUser", "limit": 5, "filters": DIRECT},
}
DAILY = {"dimensions": "ym:s:date,ym:s:lastTrafficSource", "limit": 400, "sort": "ym:s:date"}

Fetch = Callable[[dict[str, str], str], Any]


def http_fetch(params: dict[str, str], token: str) -> Any:
    req = urllib.request.Request(
        API + "?" + urllib.parse.urlencode(params),
        headers={"Authorization": f"OAuth {token}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for item in payload.get("data") or []:
        dims = [str((d or {}).get("name") or "—") for d in item.get("dimensions") or []]
        m = item.get("metrics") or []
        get = lambda i: float(m[i]) if len(m) > i and m[i] is not None else 0.0  # noqa: E731
        out.append({
            "key": " / ".join(dims),
            "visits": int(round(get(0))),
            "users": int(round(get(1))),
            "bounce": round(get(2), 1),
            "depth": round(get(3), 2),
            "duration_s": int(round(get(4))),
        })
    return out


def cut(token: str, spec: dict[str, Any], days: int, fetch: Fetch) -> dict[str, Any]:
    params = {
        "ids": COUNTER_ID,
        "metrics": METRICS,
        "dimensions": spec["dimensions"],
        "date1": f"{days}daysAgo",
        "date2": "today",
        "limit": str(spec.get("limit", 20)),
        "sort": spec.get("sort", "-ym:s:visits"),
        "accuracy": "full",
    }
    if spec.get("filters"):
        params["filters"] = spec["filters"]
    try:
        payload = fetch(params, token)
    except urllib.error.HTTPError as exc:
        return {"error": f"HTTP {exc.code}"}
    except Exception as exc:  # keep other cuts going
        return {"error": type(exc).__name__}
    return {"rows": rows(payload), "totals": [round(float(x), 2) for x in (payload.get("totals") or [])]}


def build(token: str, fetch: Fetch = http_fetch) -> dict[str, Any]:
    result: dict[str, Any] = {"schema": 1, "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "counter_id": COUNTER_ID}
    for days in (7, 30):
        result[f"last_{days}_days"] = {name: cut(token, spec, days, fetch) for name, spec in CUTS.items()}
    result["daily_30"] = cut(token, DAILY, 30, fetch)
    return result


def main() -> int:
    token = (os.getenv("YANDEX_METRIKA_OAUTH_TOKEN") or "").strip()
    if not token:
        print("TRAFFIC_BREAKDOWN_SKIP no_token")
        return 0
    data = build(token)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    errors = [f"{p}.{k}" for p in ("last_7_days", "last_30_days") for k, v in data[p].items() if "error" in v]
    print("TRAFFIC_BREAKDOWN_OK " + json.dumps({"errors": errors}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
