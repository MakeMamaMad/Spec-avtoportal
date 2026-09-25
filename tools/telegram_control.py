from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any


def telegram_call(token: str, method: str, payload: dict[str, Any] | None = None) -> Any:
    data = urllib.parse.urlencode(payload or {}).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=data,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read().decode("utf-8"))
    if not body.get("ok"):
        raise RuntimeError(body.get("description") or str(body))
    return body.get("result")


def discover_control_channel(token: str) -> str:
    webhook = telegram_call(token, "getWebhookInfo") or {}
    if webhook.get("url"):
        raise RuntimeError(
            "У бота включён webhook, поэтому автоматически определить канал через getUpdates нельзя."
        )

    updates = telegram_call(
        token,
        "getUpdates",
        {
            "timeout": 0,
            "limit": 100,
            "allowed_updates": json.dumps(["my_chat_member", "channel_post"]),
        },
    ) or []

    channels: list[tuple[int, dict[str, Any]]] = []
    for update in updates:
        for key in ("my_chat_member", "channel_post"):
            obj = update.get(key) or {}
            chat = obj.get("chat") or {}
            if chat.get("type") == "channel":
                channels.append((int(update.get("update_id") or 0), chat))

    if not channels:
        raise RuntimeError(
            "Не удалось автоматически определить Telegram-канал отчётности."
        )

    channels.sort(key=lambda item: item[0])
    preferred = [
        item
        for item in channels
        if "control" in str(item[1].get("title") or "").lower()
    ]
    return str((preferred[-1] if preferred else channels[-1])[1]["id"])


def resolve_control_chat_id(token: str) -> str:
    explicit = os.environ.get("REPORT_TELEGRAM_CHAT_ID", "").strip()
    if explicit:
        return explicit
    return discover_control_channel(token)
