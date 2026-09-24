#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = ROOT / "frontend/data/promotion/editorial_queue.json"
HISTORY_PATH = ROOT / "frontend/data/promotion/editorial_history.json"
MANUAL_QUEUE_PATH = ROOT / "frontend/data/promotion/manual_queue.json"
SUMMARY_PATH = ROOT / "frontend/data/promotion/editorial_summary.json"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def add_manual(entry: dict[str, Any], reason: str) -> None:
    data = load_json(MANUAL_QUEUE_PATH, {"schema": 1, "entries": []})
    rows = data.setdefault("entries", [])
    action_id = f"editorial:{entry.get('target_id')}:{entry.get('slug')}"
    action = {
        "action_id": action_id,
        "channel": "publisher",
        "target_id": entry.get("target_id"),
        "target_name": entry.get("target_name"),
        "action": "publish_editorial_material",
        "contact": entry.get("contact") or entry.get("target_url"),
        "status": "ready",
        "reason": reason,
        "message": entry.get("post_text"),
        "tracking_url": entry.get("site_url"),
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    for row in rows:
        if str(row.get("action_id") or "") == action_id:
            if str(row.get("status") or "") not in {"completed", "dismissed"}:
                row.update({k: v for k, v in action.items() if k != "created_at"})
            break
    else:
        rows.append(action)
    data["updated_at"] = utc_now()
    save_json(MANUAL_QUEUE_PATH, data)


def main() -> int:
    queue = load_json(QUEUE_PATH, {"entries": []})
    entries = [x for x in queue.get("entries", []) if isinstance(x, dict)]
    summary = {
        "schema": 1,
        "updated_at": utc_now(),
        "status": "nothing_planned",
        "target_name": None,
        "title": None,
        "detail": "Сегодня подходящего нового действия по отраслевым площадкам нет.",
    }

    if not entries:
        save_json(SUMMARY_PATH, summary)
        print("NO_EDITORIAL_ACTION")
        return 0

    entry = entries[0]
    summary["target_name"] = entry.get("target_name")
    summary["title"] = entry.get("title")

    if entry.get("execution") != "automatic":
        summary["status"] = "manual_prepared"
        summary["detail"] = "Материал подготовлен и добавлен в ежедневный список ручных действий."
        save_json(SUMMARY_PATH, summary)
        print("EDITORIAL_MANUAL_PREPARED")
        return 0

    if entry.get("target_id") != "mexzona":
        add_manual(entry, "Автоматического адаптера для этой площадки пока нет.")
        summary["status"] = "manual_prepared"
        summary["detail"] = "Автоматического адаптера нет; создана ручная задача."
        save_json(SUMMARY_PATH, summary)
        return 0

    env = os.environ.copy()
    env.update(
        {
            "PROMOTION_LIVE": "1",
            "PROMOTION_FORCE_RETRY": "1",
            "PROMOTION_RECURRING": "1",
            "PROMOTION_QUEUE_PATH": str(QUEUE_PATH),
            "PROMOTION_HISTORY_PATH": str(HISTORY_PATH),
        }
    )
    proc = subprocess.run(
        [sys.executable, str(ROOT / "promotion/publish_mexzona.py")],
        cwd=ROOT,
        env=env,
        check=False,
    )

    if proc.returncode == 0:
        summary["status"] = "submitted"
        summary["detail"] = "Материал автоматически отправлен в MEXZONA и найден в кабинете автора."
    else:
        add_manual(
            entry,
            "Автоматическая публикация на MEXZONA не завершилась; подготовлена ручная задача вместо повторных попыток.",
        )
        history = load_json(HISTORY_PATH, {"schema": 1, "entries": []})
        history.setdefault("entries", []).append(
            {
                "target_id": entry.get("target_id"),
                "target_name": entry.get("target_name"),
                "slug": entry.get("slug"),
                "title": entry.get("title"),
                "site_url": entry.get("site_url"),
                "created_at": utc_now(),
                "status": "manual_fallback",
            }
        )
        save_json(HISTORY_PATH, history)
        summary["status"] = "manual_fallback"
        summary["detail"] = "Автоматическая публикация не прошла; создана ручная задача."

    save_json(SUMMARY_PATH, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
