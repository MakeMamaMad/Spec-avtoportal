#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MSK = timezone(timedelta(hours=3))

CATALOG_PATH = ROOT / "frontend/data/daily_catalog_target.json"
PLACEMENT_PATH = ROOT / "frontend/data/promotion/placement_verification_summary.json"
EDITORIAL_PATH = ROOT / "frontend/data/promotion/editorial_summary.json"
TELEGRAM_PROMO_PATH = ROOT / "frontend/data/promotion/telegram_outreach_summary.json"
MANUAL_QUEUE_PATH = ROOT / "frontend/data/promotion/manual_queue.json"
MANUAL_STATE_PATH = ROOT / "frontend/data/promotion/manual_outreach_digest_state.json"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def parse_dt(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def same_moscow_day(raw: str, now: datetime) -> bool:
    value = parse_dt(raw)
    return bool(value and value.astimezone(MSK).date() == now.astimezone(MSK).date())


def after(now: datetime, hour: int, minute: int) -> bool:
    local = now.astimezone(MSK)
    return (local.hour, local.minute) >= (hour, minute)


def pending_manual_count(payload: dict[str, Any]) -> int:
    ready = {"ready", "pending", "todo"}
    return sum(
        1
        for row in payload.get("entries", [])
        if isinstance(row, dict)
        and str(row.get("status") or "").lower() in ready
    )


def next_due_action(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(MSK)
    today = local.date().isoformat()

    catalog = load_json(CATALOG_PATH, {})
    if after(now, 10, 20) and str(catalog.get("date_moscow") or "") != today:
        return "catalog"

    placements = load_json(PLACEMENT_PATH, {})
    if after(now, 11, 50) and not same_moscow_day(str(placements.get("updated_at") or ""), now):
        return "placements"

    editorial = load_json(EDITORIAL_PATH, {})
    if after(now, 12, 35) and not same_moscow_day(str(editorial.get("updated_at") or ""), now):
        return "editorial"

    telegram = load_json(TELEGRAM_PROMO_PATH, {})
    if after(now, 13, 20) and not same_moscow_day(str(telegram.get("updated_at") or ""), now):
        return "telegram_promotion"

    manual_queue = load_json(MANUAL_QUEUE_PATH, {"entries": []})
    manual_state = load_json(MANUAL_STATE_PATH, {})
    if (
        after(now, 14, 5)
        and pending_manual_count(manual_queue) > 0
        and str(manual_state.get("date_moscow") or "") != today
    ):
        return "manual_outreach"

    return ""


def main() -> int:
    action = next_due_action()
    print(f"promotion_due={action or 'none'}")
    print(action)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
