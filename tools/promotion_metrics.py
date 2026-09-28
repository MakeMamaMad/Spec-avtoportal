#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Any

COUNTER_ID = 106240080
API_URL = "https://api-metrika.yandex.net/stat/v1/data"
DIMENSIONS = "ym:s:lastUTMSource,ym:s:lastUTMMedium,ym:s:lastUTMCampaign"
METRICS = "ym:s:visits,ym:s:users,ym:s:bounceRate,ym:s:pageDepth,ym:s:avgVisitDurationSeconds"


def parse_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in payload.get("data") or []:
        dims = item.get("dimensions") or []
        metrics = item.get("metrics") or []
        names = [
            str((dim or {}).get("name") or "").strip()
            if isinstance(dim, dict)
            else str(dim or "").strip()
            for dim in dims
        ]
        while len(names) < 3:
            names.append("")
        while len(metrics) < 5:
            metrics.append(0)
        source, medium, campaign = names[:3]
        if not source:
            continue
        rows.append(
            {
                "source": source,
                "medium": medium or "—",
                "campaign": campaign or "—",
                "visits": int(round(float(metrics[0] or 0))),
                "users": int(round(float(metrics[1] or 0))),
                "bounce_rate": float(metrics[2] or 0),
                "page_depth": float(metrics[3] or 0),
                "avg_duration_seconds": float(metrics[4] or 0),
            }
        )
    rows.sort(key=lambda row: (-row["visits"], -row["users"], row["source"]))
    return rows


def fetch_promotion_metrics(
    token: str,
    *,
    days: int = 7,
    today: date | None = None,
) -> dict[str, Any]:
    token = str(token or "").strip()
    if not token:
        return {
            "status": "not_configured",
            "counter_id": COUNTER_ID,
            "days": days,
            "rows": [],
        }

    today = today or date.today()
    date1 = today - timedelta(days=max(1, days) - 1)
    params = {
        "id": str(COUNTER_ID),
        "date1": date1.isoformat(),
        "date2": today.isoformat(),
        "dimensions": DIMENSIONS,
        "metrics": METRICS,
        "attribution": "last",
        "accuracy": "full",
        "limit": "1000",
        "lang": "ru",
    }
    request = urllib.request.Request(
        API_URL + "?" + urllib.parse.urlencode(params),
        headers={
            "Authorization": f"OAuth {token}",
            "Accept": "application/json",
            "User-Agent": "SpecAvto-Control/1.0",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return {
            "status": "error",
            "counter_id": COUNTER_ID,
            "days": days,
            "rows": [],
            "error": str(exc),
        }

    return {
        "status": "ok",
        "counter_id": COUNTER_ID,
        "days": days,
        "date1": date1.isoformat(),
        "date2": today.isoformat(),
        "rows": parse_rows(payload),
        "sampled": bool(payload.get("sampled")),
        "sample_share": payload.get("sample_share"),
    }


def format_duration(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    minutes, secs = divmod(total, 60)
    if minutes:
        return f"{minutes}м {secs:02d}с"
    return f"{secs}с"


def format_feedback_lines(result: dict[str, Any], *, limit: int = 8) -> list[str]:
    status = str(result.get("status") or "")
    if status == "not_configured":
        return [
            "• API Метрики не подключён: UTM собираются на сайте, но для автоматического отчёта нужен секрет YANDEX_METRIKA_TOKEN с доступом metrika:read."
        ]
    if status == "error":
        return [
            "• Не удалось получить статистику Метрики: "
            + str(result.get("error") or "неизвестная ошибка")
        ]

    rows = result.get("rows") or []
    if not rows:
        return [f"• Переходов по UTM за последние {result.get('days') or 7} дней: 0"]

    lines = [f"• UTM-источники за последние {result.get('days') or 7} дней:"]
    for row in rows[:limit]:
        lines.append(
            "  • "
            f"{row['source']} / {row['medium']}: "
            f"{row['visits']} виз., {row['users']} польз., "
            f"глубина {row['page_depth']:.1f}, "
            f"отказы {row['bounce_rate']:.0f}%, "
            f"время {format_duration(row['avg_duration_seconds'])}"
        )
    return lines
