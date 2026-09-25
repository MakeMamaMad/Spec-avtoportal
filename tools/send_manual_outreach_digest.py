#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from telegram_control import resolve_control_chat_id, telegram_call

ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = ROOT / "frontend/data/promotion/manual_queue.json"
STATE_PATH = ROOT / "frontend/data/promotion/manual_outreach_digest_state.json"
MSK = timezone(timedelta(hours=3))
READY_STATUSES = {"ready", "pending", "todo"}


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def pending_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [
        row
        for row in payload.get("entries", [])
        if isinstance(row, dict)
        and str(row.get("status") or "").lower() in READY_STATUSES
    ]
    rows.sort(
        key=lambda row: (
            str(row.get("created_at") or ""),
            str(row.get("target_name") or row.get("target_id") or ""),
        )
    )
    return rows


def task_text(row: dict[str, Any], index: int) -> str:
    name = str(row.get("target_name") or row.get("target_id") or "Площадка")
    contact = str(row.get("contact") or "").strip() or "контакт не указан"
    reason = str(row.get("reason") or "").strip()
    message = str(row.get("message") or "").strip()

    lines = [
        f"{index}. {name}",
        f"Кому написать: {contact}",
    ]
    if reason:
        lines.append(f"Почему вручную: {reason}")
    if message:
        lines += ["", "Текст сообщения:", message]
    else:
        lines += ["", "Готового текста пока нет."]
    return "\n".join(lines).strip()


def build_messages(payload: dict[str, Any]) -> list[str]:
    rows = pending_entries(payload)
    date_text = datetime.now(MSK).strftime("%d.%m.%Y")

    if not rows:
        return [
            f"✉️ Ручные рекламные контакты — {date_text}\n\n"
            "Сегодня вручную никому писать не нужно."
        ]

    header = (
        f"✉️ Кому написать сегодня — {date_text}\n\n"
        f"Нужно связаться вручную: {len(rows)}."
    )
    messages = [header]
    for index, row in enumerate(rows, start=1):
        text = task_text(row, index)
        if len(text) <= 3900:
            messages.append(text)
            continue

        # Telegram limits one message to roughly 4096 characters.
        # Keep the contact/reason visible and split only the prepared message body.
        name = str(row.get("target_name") or row.get("target_id") or "Площадка")
        contact = str(row.get("contact") or "").strip() or "контакт не указан"
        reason = str(row.get("reason") or "").strip()
        prepared = str(row.get("message") or "").strip()
        prefix = f"{index}. {name}\nКому написать: {contact}"
        if reason:
            prefix += f"\nПочему вручную: {reason}"
        prefix += "\n\nТекст сообщения:\n"
        first_room = max(500, 3900 - len(prefix))
        messages.append(prefix + prepared[:first_room])
        rest = prepared[first_room:]
        while rest:
            messages.append(rest[:3900])
            rest = rest[3900:]

    messages.append(
        "После того как вы напишете кому-то из списка, сообщите об этом — "
        "задачу можно будет убрать из ежедневного напоминания."
    )
    return messages


def telegram_send(token: str, chat_id: str, text: str) -> None:
    telegram_call(
        token,
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        },
    )


def main() -> int:
    payload = load_json(QUEUE_PATH, {"entries": []})
    messages = build_messages(payload)

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not configured")
    chat_id = resolve_control_chat_id(token)

    for message in messages:
        telegram_send(token, chat_id, message)

    tasks = len(pending_entries(payload))
    state = {
        "schema": 1,
        "date_moscow": datetime.now(MSK).date().isoformat(),
        "sent_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "task_count": tasks,
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"MANUAL_OUTREACH_DIGEST_SENT tasks={tasks}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
