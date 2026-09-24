#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from promotion.core.manual_queue import upsert_manual_action
from promotion.core.telegram_failover import (
    BOT_UNSUPPORTED_STATUS,
    build_manual_action,
    migrate_legacy_failures,
    unsupported_target_ids,
)

TARGETS_PATH = ROOT / "promotion/telegram_targets.json"
QUEUE_PATH = ROOT / "frontend/data/telegram_promo_queue.json"
HISTORY_PATH = ROOT / "frontend/data/telegram_promo_history.json"
MANUAL_QUEUE_PATH = ROOT / "frontend/data/promotion/manual_queue.json"
SUMMARY_PATH = ROOT / "frontend/data/promotion/telegram_outreach_summary.json"


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


def save_state(
    history: dict[str, Any],
    manual_queue: dict[str, Any],
    summary: dict[str, Any],
) -> None:
    manual_queue["updated_at"] = summary["updated_at"]
    save_json(HISTORY_PATH, history)
    save_json(MANUAL_QUEUE_PATH, manual_queue)
    save_json(SUMMARY_PATH, summary)


def main() -> int:
    now = utc_now()
    targets_data = load_json(TARGETS_PATH, {"targets": []})
    queue = load_json(QUEUE_PATH, {"entries": []})
    history = load_json(HISTORY_PATH, {"schema": 1, "entries": []})
    manual_queue = load_json(MANUAL_QUEUE_PATH, {"schema": 1, "entries": []})

    targets = [x for x in targets_data.get("targets", []) if isinstance(x, dict)]
    queue_rows = [x for x in queue.get("entries", []) if isinstance(x, dict)]
    history_rows = history.setdefault("entries", [])
    manual_entries = manual_queue.setdefault("entries", [])

    migration = migrate_legacy_failures(
        history_rows,
        targets,
        queue_rows,
        manual_entries,
        now=now,
    )

    summary: dict[str, Any] = {
        "schema": 1,
        "updated_at": now,
        "status": "ready",
        "migrated_legacy_failures": migration["migrated"],
        "manual_actions_created": migration["manual_created"],
        "manual_actions_updated": migration["manual_updated"],
        "attempted_target_id": None,
        "attempted_target_name": None,
        "result": None,
        "manual_contact": None,
    }

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        summary["status"] = "token_missing"
        summary["result"] = "Автоматическое обращение не выполнялось: токен Telegram не настроен."
        save_state(history, manual_queue, summary)
        print("SKIP: TELEGRAM_BOT_TOKEN is missing")
        return 0

    already = unsupported_target_ids(history_rows)
    for row in history_rows:
        if row.get("status") in {
            "outreach_sent",
            "outreach_unavailable",
            "do_not_contact",
            BOT_UNSUPPORTED_STATUS,
        }:
            already.add(str(row.get("target_id") or ""))

    queue_by_id = {
        str(row.get("target_id")): row
        for row in queue_rows
        if row.get("target_id")
    }

    last_attempt: dict[str, str] = {}
    for hist in history_rows:
        target_id = str(hist.get("target_id") or "")
        attempted_at = str(hist.get("attempted_at") or "")
        if target_id and attempted_at and attempted_at > last_attempt.get(target_id, ""):
            last_attempt[target_id] = attempted_at

    candidates = []
    for target in targets:
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
        candidates.append((last_attempt.get(target_id, ""), target, row, bot_contact))

    candidates.sort(key=lambda item: item[0])
    if not candidates:
        summary["status"] = "no_bot_target"
        summary["result"] = "Новых рекламных ботов для автоматического обращения не осталось."
        save_state(history, manual_queue, summary)
        print("NO_BOT_OUTREACH_TARGET")
        return 0

    _, target, row, bot_contact = candidates[0]
    target_id = str(target.get("id"))
    pitch = str(row.get("outreach_pitch") or "").strip()
    summary["attempted_target_id"] = target_id
    summary["attempted_target_name"] = target.get("name")

    if not pitch:
        summary["status"] = "no_message"
        summary["result"] = "Для выбранной площадки не подготовлен текст обращения."
        save_state(history, manual_queue, summary)
        print(f"SKIP {target_id}: no outreach pitch")
        return 0

    result = send_message(token, bot_contact, pitch)
    manual_action = None
    if result.get("ok"):
        msg = result.get("result") or {}
        status = "outreach_sent"
        detail = f"message_id={msg.get('message_id')}"
        summary["status"] = "outreach_sent"
        summary["result"] = "Обращение рекламному боту площадки отправлено."
        print(f"OUTREACH_SENT {target_id} contact={bot_contact} message_id={msg.get('message_id')}")
    else:
        raw_detail = str(result.get("description") or result)[:300]
        if "USER_BOT_TO_BOT_DISABLED" in raw_detail:
            status = BOT_UNSUPPORTED_STATUS
            detail = (
                "Telegram не разрешает этому рекламному боту принимать сообщения "
                "от других ботов; автоматические повторы отключены."
            )
            manual_action = build_manual_action(target, row, created_at=now)
            if manual_action:
                outcome = upsert_manual_action(manual_entries, manual_action)
                if outcome == "created":
                    summary["manual_actions_created"] += 1
                elif outcome == "updated":
                    summary["manual_actions_updated"] += 1
                summary["status"] = "manual_required"
                summary["manual_contact"] = manual_action.get("contact")
                summary["result"] = (
                    "Автоматическое обращение невозможно. Подготовлена ручная задача "
                    "для связи с администратором."
                )
            else:
                summary["status"] = "bot_unsupported"
                summary["result"] = (
                    "Автоматическое обращение невозможно, а отдельного контакта "
                    "администратора у площадки нет."
                )
            print(f"BOT_OUTREACH_UNSUPPORTED {target_id} contact={bot_contact}")
        else:
            status = "outreach_unavailable"
            detail = raw_detail
            summary["status"] = "outreach_unavailable"
            summary["result"] = "Площадка не приняла автоматическое обращение."
            print(f"OUTREACH_UNAVAILABLE {target_id} contact={bot_contact}: {raw_detail}")

    history_rows.append({
        "target_id": target_id,
        "target_name": target.get("name"),
        "contact": bot_contact,
        "tracking_url": row.get("tracking_url"),
        "attempted_at": now,
        "status": status,
        "detail": detail,
        "manual_action_id": (
            manual_action.get("action_id")
            if manual_action
            else None
        ),
    })

    save_state(history, manual_queue, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
