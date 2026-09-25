#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
NEWS_META_PATH = ROOT / "frontend/data/news_meta.json"
TG_STATE_PATH = ROOT / "frontend/data/telegram_state.json"
VK_STATE_PATH = ROOT / "frontend/data/vk_state.json"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def parse_dt(raw: str) -> datetime | None:
    try:
        value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    except Exception:
        return None


def latest_news_slot(now: datetime) -> datetime:
    now = now.astimezone(timezone.utc)
    hour = (now.hour // 3) * 3
    return now.replace(hour=hour, minute=0, second=0, microsecond=0)


def digest_key(now: datetime, slot: str) -> str:
    return f"{now.astimezone(timezone.utc).date().isoformat()}:{slot}"


def digest_due(
    now: datetime,
    *,
    hour: int,
    minute: int,
    state: dict[str, Any],
    slot: str,
    grace_minutes: int = 7,
) -> bool:
    now = now.astimezone(timezone.utc)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now < target + timedelta(minutes=grace_minutes):
        return False
    # Stop treating an old morning digest as overdue once the evening window begins.
    if slot == "am" and now.hour >= 15:
        return False
    return digest_key(now, slot) not in (state.get("digests") or {})


def due_actions(
    now: datetime,
    news_meta: dict[str, Any],
    telegram_state: dict[str, Any],
    vk_state: dict[str, Any],
) -> list[str]:
    now = now.astimezone(timezone.utc)
    actions: list[str] = []

    latest_slot = latest_news_slot(now)
    updated_at = parse_dt(str(news_meta.get("updated_at") or ""))
    if now >= latest_slot + timedelta(minutes=12):
        if updated_at is None or updated_at < latest_slot:
            actions.append("news")

    # Telegram: 09:30 / 19:30 Moscow == 06:30 / 16:30 UTC.
    if digest_due(now, hour=6, minute=30, state=telegram_state, slot="am"):
        actions.append("telegram_am")
    if digest_due(now, hour=16, minute=30, state=telegram_state, slot="pm"):
        actions.append("telegram_pm")

    # VK: 09:40 / 19:40 Moscow == 06:40 / 16:40 UTC.
    if digest_due(now, hour=6, minute=40, state=vk_state, slot="am"):
        actions.append("vk_am")
    if digest_due(now, hour=16, minute=40, state=vk_state, slot="pm"):
        actions.append("vk_pm")

    return actions


def main() -> int:
    now = datetime.now(timezone.utc)
    actions = due_actions(
        now,
        load_json(NEWS_META_PATH, {}),
        load_json(TG_STATE_PATH, {}),
        load_json(VK_STATE_PATH, {}),
    )
    print(" ".join(actions))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
