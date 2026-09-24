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
CONFIG_PATH = ROOT / "promotion/telegram_ads_config.json"
STATE_PATH = ROOT / "frontend/data/telegram_ads_state.json"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def api_call(token: str, method: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = urllib.parse.urlencode({
        k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
        for k, v in payload.items()
    }).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/{method}", data=data)
    with urllib.request.urlopen(req, timeout=30) as response:
        body = json.loads(response.read().decode("utf-8"))
    if not body.get("ok"):
        raise RuntimeError(body.get("description") or f"Telegram {method} failed")
    return body.get("result") or {}


def main() -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("SKIP: Telegram credentials are not configured")
        return 0

    config = load_json(CONFIG_PATH, {})
    state = load_json(STATE_PATH, {"schema": 1})
    if state.get("landing_message_id"):
        print(f"LANDING_EXISTS message_id={state['landing_message_id']}")
        return 0

    site_url = str(config.get("destination", {}).get("site_tracking_url") or "https://spec-avtoportal.ru/")
    text = (
        "🚛 <b>СпецАвтоПортал</b>\n\n"
        "Отраслевые новости о грузовой и специальной технике без информационного шума. "
        "Грузовики, прицепы и полуприцепы, рынок, производители, логистика, ГОСТы и регламенты.\n\n"
        "В канале — короткие важные обновления и дайджесты. На сайте — полный архив, бренды, база знаний и нормативы."
    )
    result = api_call(token, "sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
        "disable_notification": "true",
        "reply_markup": {
            "inline_keyboard": [[{"text": "Открыть СпецАвтоПортал ↗", "url": site_url}]]
        },
    })
    message_id = result.get("message_id")
    if not isinstance(message_id, int):
        raise RuntimeError("Telegram response has no message_id")

    channel_handle = str(config.get("destination", {}).get("channel") or "@specavtoportal").lstrip("@")
    state.update({
        "schema": 1,
        "landing_message_id": message_id,
        "landing_url": f"https://t.me/{channel_handle}/{message_id}",
        "site_tracking_url": site_url,
        "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    save_json(STATE_PATH, state)
    print("LANDING_CREATED=" + json.dumps(state, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
