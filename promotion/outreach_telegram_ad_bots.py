#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.error
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


def send_message(token: str, chat_id: str, text: str) -> dict[str, Any]:
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": "false",
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"ok": False, "description": body[:300]}
        parsed["http_status"] = exc.code
        return parsed


def main() -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("SKIP: TELEGRAM_BOT_TOKEN is missing")
        return 0

    targets = load_json(TARGETS_PATH, {"targets": []})
    queue = load_json(QUEUE_PATH, {"entries": []})
    history = load_json(HISTORY_PATH, {"schema": 1, "entries": []})

    final = {"outreach_sent", "outreach_unavailable", "do_not_contact"}
    already = set()
    for row in history.get("entries", []):
        status = row.get("status")
        detail = str(row.get("detail") or "")
        # Bot-to-bot-disabled is retriable after the owner enables the feature in BotFather.
        if status == "waiting_bot_to_bot":
            continue
        if status == "outreach_unavailable" and "USER_BOT_TO_BOT_DISABLED" in detail:
            continue
        if status in final:
            already.add(str(row.get("target_id")))
    queue_by_id = {
        str(row.get("target_id")): row
        for row in queue.get("entries", [])
        if row.get("target_id")
    }

    candidate = None
    for target in targets.get("targets", []):
        target_id = str(target.get("id") or "")
        if not target_id or target_id in already:
            continue
        if target.get("status") != "approval_required":
            continue
        bot_contact = str(target.get("bot_contact") or "").strip()
        if not bot_contact and target.get("contact_type") == "advertising_bot":
            bot_contact = str(target.get("contact") or "").strip()
        if not bot_contact:
            continue
        row = queue_by_id.get(target_id)
        if not row:
            continue
        candidate = (target, row, bot_contact)
        break

    if not candidate:
        print("NO_BOT_OUTREACH_TARGET")
        return 0

    target, row, bot_contact = candidate
    target_id = str(target.get("id"))
    pitch = str(row.get("outreach_pitch") or "").strip()
    if not pitch:
        print(f"SKIP {target_id}: no outreach pitch")
        return 0

    result = send_message(token, bot_contact, pitch)
    if result.get("ok"):
        msg = result.get("result") or {}
        status = "outreach_sent"
        detail = f"message_id={msg.get('message_id')}"
        print(f"OUTREACH_SENT {target_id} contact={bot_contact} message_id={msg.get('message_id')}")
    else:
        detail = str(result.get("description") or result)[:300]
        if "USER_BOT_TO_BOT_DISABLED" in detail:
            status = "waiting_bot_to_bot"
            print(f"WAITING_BOT_TO_BOT {target_id} contact={bot_contact}: {detail}")
        else:
            status = "outreach_unavailable"
            print(f"OUTREACH_UNAVAILABLE {target_id} contact={bot_contact}: {detail}")

    history.setdefault("entries", []).append({
        "target_id": target_id,
        "target_name": target.get("name"),
        "contact": bot_contact,
        "tracking_url": row.get("tracking_url"),
        "attempted_at": utc_now(),
        "status": status,
        "detail": detail,
    })
    save_json(HISTORY_PATH, history)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
