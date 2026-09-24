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


WORKFLOW_TITLES = {
    "Video — Generate & Publish (YouTube + TikTok + Instagram)": "Публикация видео",
    "Diagnostics — Buffer Channels": "Проверка каналов Buffer",
    "Diagnostics — Instagram Test Upload": "Проверка загрузки в Instagram",
    "Diagnostics — Buffer Post Status": "Проверка публикации Buffer",
    "Diagnostics — Buffer API Connection": "Проверка подключения Buffer",
    "Diagnostics — TikTok Test Upload": "Проверка загрузки в TikTok",
    "Maintenance — Cleanup Promotion Artifact": "Очистка рекламных файлов",
    "Control — Daily Summary": "Ежедневная сводка",
    "Telegram — Editorial Digest": "Дайджест Telegram",
    "Legacy — External Article Publisher": "Старый механизм внешних публикаций",
    "Checks — News Ingest Tests": "Проверка загрузки новостей",
    "News — Fetch & Publish": "Обновление новостей",
    "Control — Telegram Test": "Проверка канала отчётности",
    "Site — Build, Deploy & VK Publish": "Обновление сайта",
    "Legacy — External Article Promotion Queue": "Старая очередь внешнего продвижения",
    "Checks — Full QA": "Полная проверка проекта",
    "Maintenance — Safe Auto Merge": "Проверка безопасного объединения изменений",
    "Video — Preview Generator": "Предпросмотр видео",
    "Promotion — Daily Site Advertising": "Продвижение сайта",
    "Promotion — Prepare Telegram Ads": "Подготовка Telegram Ads",
    "Promotion — Telegram Outreach": "Внешнее продвижение в Telegram",
    "Promotion — Verify Placements": "Проверка рекламных размещений",
    "Legacy — Verify MEXZONA Promotion": "Проверка публикации на MEXZONA",
    "VK — Editorial Digest": "Дайджест VK",
}


SUCCESS_MESSAGES = {
    "Video — Generate & Publish (YouTube + TikTok + Instagram)": "Видео подготовлено и обработано для публикации в подключённых соцсетях.",
    "Diagnostics — Buffer Channels": "Подключённые каналы Buffer проверены.",
    "Diagnostics — Instagram Test Upload": "Тестовая загрузка в Instagram завершилась успешно.",
    "Diagnostics — Buffer Post Status": "Состояние публикации в Buffer проверено.",
    "Diagnostics — Buffer API Connection": "Связь с Buffer работает.",
    "Diagnostics — TikTok Test Upload": "Тестовая загрузка в TikTok завершилась успешно.",
    "Maintenance — Cleanup Promotion Artifact": "Служебные рекламные файлы очищены.",
    "Control — Daily Summary": "Ежедневная сводка состояния автоматизации подготовлена и отправлена.",
    "Telegram — Editorial Digest": "Редакционный дайджест Telegram обработан.",
    "Legacy — External Article Publisher": "Старый механизм внешних публикаций проверен; активная рекламная отправка не выполнялась.",
    "Checks — News Ingest Tests": "Проверки загрузки и обработки новостей прошли без ошибок.",
    "News — Fetch & Publish": "Источники новостей проверены, база сайта обновлена, новые важные материалы обработаны для Telegram.",
    "Control — Telegram Test": "Связь с каналом отчётности подтверждена.",
    "Site — Build, Deploy & VK Publish": "Сайт собран и опубликован; важные материалы обработаны для VK.",
    "Legacy — External Article Promotion Queue": "Старая очередь внешнего продвижения обновлена.",
    "Checks — Full QA": "Полная проверка проекта завершилась без ошибок.",
    "Maintenance — Safe Auto Merge": "Автоматическая проверка возможности безопасно объединить изменения завершена.",
    "Video — Preview Generator": "Предпросмотр видео подготовлен.",
    "Promotion — Daily Site Advertising": "Дневной проход по площадкам для продвижения сайта завершён.",
    "Promotion — Prepare Telegram Ads": "Посадочная публикация и пакет для Telegram Ads подготовлены.",
    "Promotion — Telegram Outreach": "Очередь внешнего продвижения в Telegram обработана.",
    "Promotion — Verify Placements": "Проверены ранее отправленные заявки и состояние опубликованных размещений.",
    "Legacy — Verify MEXZONA Promotion": "Проверка публикации на MEXZONA завершена.",
    "VK — Editorial Digest": "Редакционный дайджест VK обработан.",
}


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
    lines = ["Что произошло с каталогами:"]
    for row in attempts[-8:]:
        name = str(row.get("target_name") or row.get("target_id") or "Каталог")
        status = str(row.get("status") or "")
        detail = str(row.get("detail") or "")
        if status in {"submitted", "accepted", "published"}:
            result = "заявка отправлена"
        elif status == "under_moderation":
            result = "заявка отправлена на модерацию"
        elif status == "needs_manual" and ("CAPTCHA" in detail.upper() or "verification" in detail.lower()):
            result = "пропущен — нужна ручная проверка"
        elif status == "needs_manual":
            result = "пропущен — нужно ручное действие"
        elif status == "technical_failure":
            result = "пропущен — автоматическая отправка не подошла"
        elif status == "unavailable":
            result = "пропущен — площадка недоступна"
        elif status == "rejected":
            result = "заявка отклонена"
        else:
            result = "проверен"
        lines.append(f"• {name}: {result}")
    if not attempts:
        lines.append("• Новых попыток размещения не было.")
    elif not any(x.get("status") in {"submitted", "under_moderation", "published", "accepted"} for x in attempts):
        lines.append("• Нового автоматического размещения нет; неподходящие площадки пропущены.")
    return lines


def telegram_promo_details() -> list[str]:
    hist = load_json(ROOT / "frontend/data/telegram_promo_history.json", {"entries": []})
    rows = [x for x in hist.get("entries", []) if isinstance(x, dict)]
    if not rows:
        return ["Что произошло: новых попыток внешнего размещения не было."]
    row = rows[-1]
    status = str(row.get("status") or "")
    detail = str(row.get("detail") or "")
    if status == "published":
        return [f"Что произошло: размещение опубликовано в {row.get('target_name') or row.get('target_id')}."]
    if status in {"waiting_bot_to_bot", "outreach_unavailable"} and "USER_BOT_TO_BOT_DISABLED" in detail:
        return [
            "Что произошло: автоматическое обращение к рекламной площадке не прошло.",
            "Причина на стороне площадки; дополнительных действий от владельца портала сейчас не требуется.",
        ]
    return ["Что произошло: новых внешних размещений пока нет."]


def ads_details() -> list[str]:
    state = load_json(ROOT / "frontend/data/telegram_ads_state.json", {})
    if state.get("landing_url"):
        return [f"Посадочная публикация готова: {state.get('landing_url')}"]
    return ["Посадочная публикация пока не найдена."]


def ingest_details() -> list[str]:
    news = load_json(ROOT / "frontend/data/news.json", [])
    if isinstance(news, list):
        return [f"Сейчас на сайте {len(news)} материалов в базе новостей."]
    return []


def placement_verification_details() -> list[str]:
    summary = load_json(
        ROOT / "frontend/data/promotion/placement_verification_summary.json",
        {},
    )
    checked = int(summary.get("checked") or 0)
    created = int(summary.get("created") or 0)
    states = summary.get("states") or {}
    lines = []
    if created:
        lines.append(f"Добавлено в наблюдение новых заявок: {created}.")
    if checked:
        lines.append(f"Проверено размещений: {checked}.")
    else:
        lines.append("Сегодня не было размещений, срок проверки которых уже наступил.")

    live = int(states.get("live") or 0)
    pending = int(states.get("pending_review") or 0) + int(states.get("still_pending") or 0)
    rejected = int(states.get("rejected") or 0)
    removed = int(states.get("removed") or 0)
    lines.append(
        f"Сейчас подтверждено публикаций: {live}; ожидают подтверждения: {pending}; "
        f"отклонено: {rejected}; снято с публикации: {removed}."
    )

    for row in (summary.get("changes") or [])[-5:]:
        name = str(row.get("target_name") or row.get("target_id") or "Площадка")
        after = str(row.get("after") or "")
        if after == "live":
            lines.append(f"• {name}: публикация подтверждена.")
        elif after == "rejected":
            lines.append(f"• {name}: заявка отклонена.")
        elif after == "removed":
            lines.append(f"• {name}: ранее найденная публикация больше не доступна.")
    return lines


def human_title(name: str) -> str:
    return WORKFLOW_TITLES.get(name, "Автоматическая задача")


def human_result(name: str, conclusion: str) -> str:
    if conclusion == "success":
        return SUCCESS_MESSAGES.get(name, "Задача завершилась успешно.")
    return {
        "failure": "Задача завершилась с ошибкой.",
        "cancelled": "Задача была отменена.",
        "skipped": "Задача была пропущена.",
        "timed_out": "Задача не успела завершиться вовремя.",
    }.get(conclusion, "Задача завершена.")


def main() -> int:
    event_path = Path(os.environ.get("GITHUB_EVENT_PATH", ""))
    event = load_json(event_path, {})
    run = event.get("workflow_run") or {}

    name = str(run.get("name") or "")
    conclusion = str(run.get("conclusion") or "unknown")
    run_url = str(run.get("html_url") or "")

    lines = [
        f"{status_icon(conclusion)} {human_title(name)}",
        "",
        human_result(name, conclusion),
    ]

    if name == "Promotion — Daily Site Advertising":
        lines += [""] + catalog_details()
    elif name == "Promotion — Telegram Outreach":
        lines += [""] + telegram_promo_details()
    elif name == "Promotion — Prepare Telegram Ads":
        lines += [""] + ads_details()
    elif name == "Promotion — Verify Placements":
        lines += [""] + placement_verification_details()
    elif name == "News — Fetch & Publish":
        lines += [""] + ingest_details()

    if run_url:
        lines += ["", f"Подробности: {run_url}"]

    lines += ["", f"SpecAvto Control · {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M UTC')}"]

    out = Path(os.environ.get("OPS_REPORT_PATH", "/tmp/specavto-report.md"))
    out.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
