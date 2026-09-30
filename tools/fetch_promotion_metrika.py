#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "frontend/data/promotion/traffic_summary.json"
COUNTER_ID = "106240080"
MSK = timezone(timedelta(hours=3))
TRACKED_CAMPAIGNS = {
    "catalog_promotion",
    "industry_editorial",
    "industry_promotion",
    "community_promotion",
    "telegram_ads",
}
# Our own posts (Telegram channel, Dzen, VK) are tagged utm_medium=social with a
# per-post campaign (axle_calculator, dzen_articles, ...): count them too.
OWN_MEDIUMS = {"social", "editorial", "email"}


def save_json(value: Any) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fetch_report(token: str) -> dict[str, Any]:
    params = {
        "ids": COUNTER_ID,
        "dimensions": "ym:s:lastUTMSource,ym:s:lastUTMMedium,ym:s:lastUTMCampaign",
        "metrics": (
            "ym:s:visits,ym:s:users,ym:s:bounceRate,"
            "ym:s:pageDepth,ym:s:avgVisitDurationSeconds"
        ),
        "date1": "7daysAgo",
        "date2": "today",
        "accuracy": "full",
        "limit": "1000",
        "sort": "-ym:s:visits",
        "lang": "ru",
    }
    url = "https://api-metrika.yandex.net/stat/v1/data?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"OAuth {token}",
            "Accept": "application/json",
            "User-Agent": "SpecAvto-Promotion-Analytics",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in payload.get("data") or []:
        dims = item.get("dimensions") or []
        metrics = item.get("metrics") or []
        source = str((dims[0] or {}).get("name") or "").strip() if len(dims) > 0 else ""
        medium = str((dims[1] or {}).get("name") or "").strip() if len(dims) > 1 else ""
        campaign = str((dims[2] or {}).get("name") or "").strip() if len(dims) > 2 else ""
        if not source or not (campaign in TRACKED_CAMPAIGNS or (campaign and medium in OWN_MEDIUMS)):
            continue
        rows.append(
            {
                "source": source,
                "medium": medium,
                "campaign": campaign,
                "visits": int(round(float(metrics[0] if len(metrics) > 0 else 0))),
                "users": int(round(float(metrics[1] if len(metrics) > 1 else 0))),
                "bounce_rate": round(float(metrics[2] if len(metrics) > 2 else 0), 1),
                "page_depth": round(float(metrics[3] if len(metrics) > 3 else 0), 2),
                "avg_visit_duration_seconds": int(round(float(metrics[4] if len(metrics) > 4 else 0))),
            }
        )
    rows.sort(key=lambda row: (-row["visits"], row["source"]))
    return rows


def main() -> int:
    token = os.environ.get("YANDEX_METRIKA_OAUTH_TOKEN", "").strip()
    base = {
        "schema": 1,
        "updated_at": utc_now(),
        "counter_id": COUNTER_ID,
        "period": "7daysAgo..today",
        "status": "ok",
        "sources": [],
        "totals": {"visits": 0, "users": 0},
    }

    if not token:
        base["status"] = "missing_token"
        base["detail"] = (
            "Для автоматического отчёта по рекламным UTM нужен секрет "
            "YANDEX_METRIKA_OAUTH_TOKEN с доступом metrika:read."
        )
        save_json(base)
        print("METRIKA_PROMOTION_ANALYTICS_MISSING_TOKEN")
        return 0

    try:
        payload = fetch_report(token)
        rows = normalize(payload)
    except Exception as exc:
        base["status"] = "error"
        base["detail"] = f"Не удалось получить отчёт Метрики: {type(exc).__name__}"
        save_json(base)
        print(f"METRIKA_PROMOTION_ANALYTICS_ERROR {type(exc).__name__}")
        return 0

    base["sources"] = rows
    base["totals"] = {
        "visits": sum(int(row["visits"]) for row in rows),
        "users": sum(int(row["users"]) for row in rows),
    }
    base["sampled"] = bool(payload.get("sampled"))
    base["sample_share"] = payload.get("sample_share")
    save_json(base)
    print(
        "METRIKA_PROMOTION_ANALYTICS_OK "
        f"sources={len(rows)} visits={base['totals']['visits']} users={base['totals']['users']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
