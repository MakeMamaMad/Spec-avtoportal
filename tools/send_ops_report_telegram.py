#!/usr/bin/env python3
from __future__ import annotations

import os
import re
from pathlib import Path

from telegram_control import resolve_control_chat_id, telegram_call


def clean_markdown(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1: \2", text)
    text = text.replace("**", "").replace("_", "")
    return text.strip()


def main() -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    report_path = Path(os.getenv("OPS_REPORT_PATH", "/tmp/specavto-report.md"))

    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    if not report_path.exists():
        print("Report file is missing; Telegram report skipped.")
        return 0

    text = clean_markdown(report_path.read_text(encoding="utf-8"))
    if len(text) > 3900:
        text = text[:3890].rstrip() + "…"

    chat_id = resolve_control_chat_id(token)
    telegram_call(
        token,
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        },
    )
    print("Telegram ops report sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
