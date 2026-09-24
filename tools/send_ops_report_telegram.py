#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path


def clean_markdown(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1: \2", text)
    text = text.replace("**", "").replace("_", "")
    return text.strip()


def main() -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("REPORT_TELEGRAM_CHAT_ID", "").strip()
    report_path = Path(os.getenv("OPS_REPORT_PATH", "/tmp/specavto-report.md"))

    if not chat_id:
        print("REPORT_TELEGRAM_CHAT_ID is not configured; Telegram report skipped.")
        return 0
    if not token:
        print("TELEGRAM_BOT_TOKEN is not configured; Telegram report skipped.")
        return 0
    if not report_path.exists():
        print("Report file is missing; Telegram report skipped.")
        return 0

    text = clean_markdown(report_path.read_text(encoding="utf-8"))
    if len(text) > 3900:
        text = text[:3890].rstrip() + "…"

    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        body = json.loads(response.read().decode("utf-8"))
    if not body.get("ok"):
        raise RuntimeError(body.get("description") or "Telegram report failed")
    print("Telegram ops report sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
