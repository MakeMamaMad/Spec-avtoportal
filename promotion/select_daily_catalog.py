#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGETS_PATH = ROOT / "promotion/site_targets.json"
HISTORY_PATH = ROOT / "frontend/data/site_promo_history.json"
SELECTED_PATH = ROOT / "frontend/data/daily_catalog_target.json"

MSK = timezone(timedelta(hours=3))
FINAL_STATUSES = {
    "submitted",
    "under_moderation",
    "published",
    "accepted",
    "rejected",
    "technical_failure",
    "needs_manual",
    "unavailable",
}


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_when(row: dict[str, Any]) -> datetime | None:
    for key in ("attempted_at", "submitted_at", "published_at"):
        raw = str(row.get(key) or "").strip()
        if not raw:
            continue
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
    return None


def main() -> int:
    targets = load_json(TARGETS_PATH, {"targets": []})
    history = load_json(HISTORY_PATH, {"entries": []})
    rows = [x for x in history.get("entries", []) if isinstance(x, dict)]

    today_msk = datetime.now(MSK).date()
    for row in rows:
        when = parse_when(row)
        if when and when.astimezone(MSK).date() == today_msk:
            selected = {
                "schema": 1,
                "date_moscow": str(today_msk),
                "target_id": "none",
                "reason": "daily_limit_already_used",
                "existing_target_id": row.get("target_id"),
            }
            save_json(SELECTED_PATH, selected)
            print("none")
            return 0

    attempted = {
        str(row.get("target_id"))
        for row in rows
        if row.get("target_id") and row.get("status") in FINAL_STATUSES
    }

    selected_target = None
    for target in targets.get("targets", []):
        if not isinstance(target, dict):
            continue
        target_id = str(target.get("id") or "")
        status = str(target.get("status") or "")
        if not target_id or target_id in attempted:
            continue
        if status in {"blocked", "do_not_post", "paused", "paused_dns", "disabled"}:
            continue
        selected_target = target
        break

    if not selected_target:
        selected = {
            "schema": 1,
            "date_moscow": str(today_msk),
            "target_id": "none",
            "reason": "no_unused_active_targets",
        }
        save_json(SELECTED_PATH, selected)
        print("none")
        return 0

    selected = {
        "schema": 1,
        "date_moscow": str(today_msk),
        "target_id": selected_target.get("id"),
        "target_name": selected_target.get("name"),
        "submission_url": selected_target.get("url"),
        "selected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    save_json(SELECTED_PATH, selected)
    print(selected_target.get("id"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
