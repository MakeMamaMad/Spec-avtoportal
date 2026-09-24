#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def status_icon(conclusion: str) -> str:
    return {
        "success": "✅",
        "failure": "❌",
        "cancelled": "⚪",
        "skipped": "⏭️",
        "timed_out": "⏱️",
    }.get(conclusion, "ℹ️")


def catalog_details() -> list[str]:
    summary = load_json(ROOT / "frontend/data/daily_catalog_target.json", {})
    attempts = summary.get("attempts") or []
    lines = ["**Каталоги:**"]
    for row in attempts[-8:]:
        name = str(row.get("target_name") or row.get("target_id") or "Каталог")
        status = str(row.get("status") or "")
        detail = str(row.get("detail") or "")
        if status in {"submitted", "accepted", "published"}:
            result = "✅ заявка отправлена"
        elif status == "under_moderation":
            result = "✅ отправлено на модерацию"
        elif status == "needs_manual" and ("CAPTCHA" in detail.upper() or "verification" in detail.lower()):
            result = "⏭️ пропущен — требуется CAPTCHA/ручная проверка"
        elif status == "needs_manual":
            result = "⏭️ пропущен — требуется ручное действие"
        elif status == "technical_failure":
            result = "⏭️ пропущен — форма не подходит для автоматической отправки"
        elif status == "unavailable":
            result = "⏭️ пропущен — каталог недоступен"
        elif status == "rejected":
            result = "❌ заявка отклонена"
        else:
            result = "ℹ️ проверен"
        lines.append(f"- {name}: {result}")
    if attempts and not any(x.get("status") in {"submitted", "under_moderation", "published", "accepted"} for x in attempts):
        lines.append("- Итог: нового автоматического размещения нет; неподходящие каталоги отсеяны.")
    return lines


def telegram_promo_details() -> list[str]:
    hist = load_json(ROOT / "frontend/data/telegram_promo_history.json", {"entries": []})
    rows = [x for x in hist.get("entries", []) if isinstance(x, dict)]
    if not rows:
        return []
    row = rows[-1]
    status = str(row.get("status") or "")
    detail = str(row.get("detail") or "")
    if status == "published":
        return [f"**Telegram promotion:** ✅ размещение опубликовано — {row.get('target_name') or row.get('target_id')}"]
    if status in {"waiting_bot_to_bot", "outreach_unavailable"} and "USER_BOT_TO_BOT_DISABLED" in detail:
        return [
            "**Telegram promotion:** ⏸️ автоматическое обращение к рекламной площадке пока недоступно.",
            "- Причина на стороне рекламного бота площадки. От владельца SpecAvtoPortal действий не требуется.",
        ]
    return ["**Telegram promotion:** ℹ️ новых внешних размещений пока нет."]


def ads_details() -> list[str]:
    state = load_json(ROOT / "frontend/data/telegram_ads_state.json", {})
    if state.get("landing_url"):
        return [f"**Telegram Ads landing:** {state.get('landing_url')}"]
    return []


def ingest_details() -> list[str]:
    news = load_json(ROOT / "frontend/data/news.json", [])
    if isinstance(news, list):
        return [f"**Новости на сайте:** {len(news)} материалов в текущей базе."]
    return []


def main() -> int:
    event_path = Path(os.environ.get("GITHUB_EVENT_PATH", ""))
    event = load_json(event_path, {})
    run = event.get("workflow_run") or {}

    name = str(run.get("name") or "GitHub workflow")
    conclusion = str(run.get("conclusion") or "unknown")
    run_url = str(run.get("html_url") or "")
    branch = str(run.get("head_branch") or "")
    sha = str(run.get("head_sha") or "")[:8]
    event_name = str(run.get("event") or "")
    created = str(run.get("created_at") or "")
    updated = str(run.get("updated_at") or "")

    if name == "Checks — Full QA" and conclusion == "success":
        print("SKIP_REPORT")
        return 0

    human_conclusion = {
        "success": "успешно",
        "failure": "ошибка",
        "cancelled": "отменено",
        "skipped": "пропущено",
        "timed_out": "тайм-аут",
    }.get(conclusion, conclusion)

    lines = [
        f"### {status_icon(conclusion)} {name} — {human_conclusion}",
        "",
        f"- Ветка: {branch}",
        f"- Commit: {sha}",
        f"- Trigger: {event_name}",
    ]
    if created:
        lines.append(f"- Старт: {created}")
    if updated:
        lines.append(f"- Завершение: {updated}")

    if name == "Promotion — Daily Site Advertising":
        lines += [""] + catalog_details()
    elif name == "Promotion — Telegram Outreach":
        lines += [""] + telegram_promo_details()
    elif name == "Promotion — Prepare Telegram Ads":
        lines += [""] + ads_details()
    elif name == "Ingest & Publish":
        lines += [""] + ingest_details()

    if run_url:
        lines += ["", f"[Открыть GitHub Actions run]({run_url})"]

    lines += ["", f"_SpecAvto Control · {datetime.now(timezone.utc).isoformat(timespec='seconds')}_"]

    out = Path(os.environ.get("OPS_REPORT_PATH", "/tmp/specavto-report.md"))
    out.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
