#!/usr/bin/env python3
"""One-time public smoke test for Telegram and VK publishing."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGGREGATOR = ROOT / "aggregator"
if str(AGGREGATOR) not in sys.path:
    sys.path.insert(0, str(AGGREGATOR))

from telegram_visual import render_important_card
from post_to_telegram import send_photo as telegram_send_photo, send_message as telegram_send_message
from post_to_vk import (
    load_config as load_vk_config,
    resolve_group_id,
    send_with_visual_fallback,
)

SITE_URL = "https://spec-avtoportal.ru/?utm_source=social&utm_medium=smoke&utm_campaign=channels_live"

ITEM = {
    "title": "СпецАвтоПортал — автопубликация подключена",
    "summary": "Проверяем доставку фирменных карточек в Telegram и VK. Дальше — только редакционные новости и дайджесты.",
    "tags": ["Отрасль"],
}


def run_telegram(card_path: Path) -> tuple[int, str]:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("Telegram secrets are missing")

    caption = (
        "<b>СпецАвтоПортал — автопубликация подключена</b>\n\n"
        "Проверяем доставку фирменных карточек. "
        "Дальше в канале — только редакционные новости и дайджесты.\n\n"
        f'🔗 <a href="{SITE_URL}">spec-avtoportal.ru</a>'
    )
    try:
        message_id = telegram_send_photo(
            token,
            chat_id,
            card_path,
            caption,
            SITE_URL,
        )
        return message_id, "visual"
    except Exception as exc:
        print(f"WARN: Telegram visual smoke failed, fallback to text: {exc}", file=sys.stderr)
        message_id = telegram_send_message(
            token,
            chat_id,
            caption,
            site_url=SITE_URL,
            disable_preview=True,
        )
        return message_id, "text_fallback"


def run_vk() -> tuple[int, str]:
    token = os.getenv("VK_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("VK_ACCESS_TOKEN is missing")

    config = load_vk_config()
    api_version = str(config.get("api_version") or "5.199")
    group_id = resolve_group_id(
        token,
        api_version,
        str(config.get("community_screen_name") or "specavtoportal"),
        os.getenv("VK_GROUP_ID", "").strip(),
    )

    message = (
        "✅ СпецАвтоПортал — автопубликация подключена\n\n"
        "Проверяем доставку фирменных карточек в VK. "
        "Дальше здесь — важные новости отрасли и утренние/вечерние сводки.\n\n"
        f"Сайт: {SITE_URL}"
    )
    return send_with_visual_fallback(
        token,
        api_version,
        group_id,
        message,
        kind="important",
        key="social-smoke-2026-09-23",
        item=ITEM,
    )


def main() -> int:
    errors: list[str] = []

    with tempfile.TemporaryDirectory(prefix="specavto-social-smoke-") as tmp:
        card_path = Path(tmp) / "channels-live.png"
        render_important_card(ITEM, card_path)

        try:
            message_id, mode = run_telegram(card_path)
            print(f"TELEGRAM_SMOKE_OK message_id={message_id} mode={mode}")
        except Exception as exc:
            errors.append(f"Telegram: {exc}")
            print(f"TELEGRAM_SMOKE_ERROR {exc}", file=sys.stderr)

        try:
            post_id, mode = run_vk()
            print(f"VK_SMOKE_OK post_id={post_id} mode={mode}")
        except Exception as exc:
            errors.append(f"VK: {exc}")
            print(f"VK_SMOKE_ERROR {exc}", file=sys.stderr)

    if errors:
        print("Smoke test completed with errors: " + " | ".join(errors), file=sys.stderr)
        return 1

    print("SOCIAL_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
