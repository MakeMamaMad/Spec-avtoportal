#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGETS_PATH = ROOT / "promotion/telegram_targets.json"
QUEUE_PATH = ROOT / "frontend/data/telegram_promo_queue.json"
HISTORY_PATH = ROOT / "frontend/data/telegram_promo_history.json"


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


def api_call(token: str, method: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=data,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("SKIP: TELEGRAM_BOT_TOKEN is missing")
        return 0

    targets = load_json(TARGETS_PATH, {"targets": []})
    queue = load_json(QUEUE_PATH, {"entries": []})
    history = load_json(HISTORY_PATH, {"schema": 1, "entries": []})

    published = {
        str(x.get("target_id"))
        for x in history.get("entries", [])
        if x.get("status") == "published"
    }
    queue_by_id = {str(x.get("target_id")): x for x in queue.get("entries", [])}

    attempts = 0
    for target in targets.get("targets", []):
        target_id = str(target.get("id") or "")
        if target.get("status") != "approved":
            continue
        if not target.get("approval_record"):
            print(f"SKIP {target_id}: approved status has no approval_record")
            continue
        if target_id in published:
            continue

        row = queue_by_id.get(target_id)
        if not row:
            print(f"SKIP {target_id}: no prepared queue entry")
            continue

        chat_id = str(target.get("chat_id") or target.get("handle") or "").strip()
        if not chat_id:
            print(f"SKIP {target_id}: no chat_id/handle")
            continue

        attempts += 1
        try:
            result = api_call(token, "sendMessage", {
                "chat_id": chat_id,
                "text": row.get("ad_copy") or "",
                "disable_web_page_preview": "false",
            })
            if not result.get("ok"):
                raise RuntimeError(str(result))
            message = result.get("result") or {}
            history.setdefault("entries", []).append({
                "target_id": target_id,
                "target_name": target.get("name"),
                "handle": target.get("handle"),
                "tracking_url": row.get("tracking_url"),
                "message_id": message.get("message_id"),
                "published_at": utc_now(),
                "status": "published",
            })
            print(f"PUBLISHED {target_id} message_id={message.get('message_id')}")
        except Exception as exc:
            history.setdefault("entries", []).append({
                "target_id": target_id,
                "target_name": target.get("name"),
                "handle": target.get("handle"),
                "attempted_at": utc_now(),
                "status": "waiting_bot_access",
                "detail": f"{type(exc).__name__}: {exc}"[:300],
            })
            print(f"WAITING_BOT_ACCESS {target_id}: {type(exc).__name__}")

    save_json(HISTORY_PATH, history)
    print(f"Approved-target attempts: {attempts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
