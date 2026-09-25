#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "tools/autoposter/state/video_schedule.json"
MSK = ZoneInfo("Europe/Moscow")


def load_state(path: Path = STATE_PATH) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"schema": 1, "days": {}}


def slot_published(state: dict, day: str, slot: str) -> bool:
    return ((state.get("days") or {}).get(day) or {}).get(slot) == "published"


def due_slot(now: datetime, state: dict) -> str:
    local = now.astimezone(MSK)
    day = local.date().isoformat()
    minutes = local.hour * 60 + local.minute

    # Recovery windows are deliberately wider than the desired publication
    # times because GitHub scheduled events can be delayed.
    if 10 * 60 + 25 <= minutes < 15 * 60:
        return "" if slot_published(state, day, "am") else "am"
    if 18 * 60 + 25 <= minutes < 23 * 60:
        return "" if slot_published(state, day, "pm") else "pm"
    return ""


def main() -> int:
    now = datetime.now(MSK)
    state = load_state()
    slot = due_slot(now, state)
    today = now.astimezone(MSK).date().isoformat()
    day_state = (state.get("days") or {}).get(today) or {}
    print(f"moscow={now.isoformat()} state={day_state} due_slot={slot or 'none'}")
    print(slot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
