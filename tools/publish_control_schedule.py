#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from telegram_control import resolve_control_chat_id, telegram_call


def build_schedule_text() -> str:
    return """📌 Расписание SpecAvtoPortal

Все времена — по Москве.

📰 Новости
• Каждые 3 часа — поиск и обновление новостей на сайте.
• Важные новости после обработки могут автоматически уйти в Telegram и VK.

📣 Telegram и VK
• 09:30 — утренний дайджест Telegram.
• 09:40 — утренний дайджест VK.
• 19:30 — вечерний дайджест Telegram.
• 19:40 — вечерний дайджест VK.

🎬 Shorts
• 10:30 — первый ролик в YouTube Shorts, TikTok и Instagram Reels.
• 18:30 — второй ролик в YouTube Shorts, TikTok и Instagram Reels.
• Если основной запуск задержался, система проверяет пропущенный слот после обновления новостей и может восстановить публикацию автоматически.

📚 Продвижение сайта
• 10:15 — попытка размещения сайта в каталогах.
• 11:45 — проверка ранее отправленных заявок: опубликованы они реально или ещё ждут модерации.
• 12:30 — отраслевое продвижение собственных материалов; автоматические площадки обрабатываются без вашего участия.
• 13:15 — внешнее продвижение через Telegram-площадки.
• 14:00 — сообщение «Кому написать сегодня», если где-то требуется ваше ручное действие.

📊 Контроль
• После успешных автоматизаций — короткий отчёт сюда, в SpecAvto Control.
• 20:45 — итоговая сводка за день.

Если автоматизация справилась сама, в отчёте будет написано, что от вас действий не требуется.
Если понадобится ваше участие, бот отдельно напишет кому, куда и какой текст отправить.
"""


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

    chat_id = resolve_control_chat_id(token)
    result = telegram_call(
        token,
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": build_schedule_text(),
            "disable_web_page_preview": "true",
        },
    )
    message_id = int((result or {}).get("message_id") or 0)
    if not message_id:
        raise RuntimeError("Telegram did not return message_id for schedule message")

    telegram_call(
        token,
        "pinChatMessage",
        {
            "chat_id": chat_id,
            "message_id": message_id,
            "disable_notification": "true",
        },
    )
    print(f"CONTROL_SCHEDULE_PINNED message_id={message_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
