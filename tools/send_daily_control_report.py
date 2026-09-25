#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from telegram_control import resolve_control_chat_id, telegram_call

ROOT = Path(__file__).resolve().parents[1]
MSK = timezone(timedelta(hours=3))


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def parse_dt(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def is_today(raw: str) -> bool:
    dt = parse_dt(raw)
    return bool(dt and dt.astimezone(MSK).date() == datetime.now(MSK).date())


def github_get(path: str) -> Any:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token or not repo:
        return None
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "SpecAvto-Control",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def latest_run(runs: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    matches = [r for r in runs if r.get("name") == name and is_today(str(r.get("created_at") or ""))]
    return matches[0] if matches else None


def human_run_status(value: str) -> str:
    return {
        "success": "✅ работает",
        "failure": "❌ ошибка",
        "cancelled": "⚪ отменён",
        "skipped": "⏭️ пропущен",
        "in_progress": "⏳ выполняется",
        "queued": "⏳ в очереди",
    }.get(value, value or "нет данных")


def run_status(runs: list[dict[str, Any]], name: str) -> str:
    row = latest_run(runs, name)
    if not row:
        return "не запускался"
    status = str(row.get("conclusion") or row.get("status") or "")
    return human_run_status(status)


def human_catalog_result(row: dict[str, Any]) -> str:
    name = str(row.get("target_name") or row.get("target_id") or "Каталог")
    status = str(row.get("status") or "")
    detail = str(row.get("detail") or "")

    if status in {"submitted", "accepted", "published"}:
        return f"• {name}: ✅ заявка отправлена"
    if status == "under_moderation":
        return f"• {name}: ✅ отправлено на модерацию"
    if status == "needs_manual":
        if "CAPTCHA" in detail.upper() or "verification" in detail.lower():
            return f"• {name}: ⏭️ пропущен — требуется CAPTCHA/ручная проверка"
        return f"• {name}: ⏭️ пропущен — требуется ручное действие"
    if status == "technical_failure":
        return f"• {name}: ⏭️ пропущен — форма не подходит для автоматической отправки"
    if status == "unavailable":
        return f"• {name}: ⏭️ пропущен — каталог сейчас недоступен"
    if status == "rejected":
        return f"• {name}: ❌ заявка отклонена"
    return f"• {name}: ℹ️ проверен"


def telegram_promo_summary(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "• Сегодня новых попыток не было"
    published = [r for r in rows if r.get("status") == "published"]
    if published:
        latest = published[-1]
        return f"• ✅ Размещение опубликовано: {latest.get('target_name') or latest.get('target_id')}"
    blocked = [
        r for r in rows
        if r.get("status") in {"waiting_bot_to_bot", "outreach_unavailable"}
        and "USER_BOT_TO_BOT_DISABLED" in str(r.get("detail") or "")
    ]
    if blocked:
        return "• ⏸️ Автоматические обращения пока не проходят: рекламные боты площадок не принимают сообщения от других ботов. От вас действий не требуется."
    return "• ℹ️ Новых размещений сегодня нет"


def main() -> int:
    today = datetime.now(MSK).date()
    news = load_json(ROOT / "frontend/data/news.json", [])
    tg = load_json(ROOT / "frontend/data/telegram_state.json", {})
    vk = load_json(ROOT / "frontend/data/vk_state.json", {})
    catalogs = load_json(ROOT / "frontend/data/site_promo_history.json", {"entries": []})
    tg_promo = load_json(ROOT / "frontend/data/telegram_promo_history.json", {"entries": []})
    ads = load_json(ROOT / "frontend/data/telegram_ads_state.json", {})

    runs_data = github_get("actions/runs?per_page=100") or {}
    runs = runs_data.get("workflow_runs") or []

    tg_digests = [
        d for d in (tg.get("digests") or {}).values()
        if is_today(str(d.get("sent_at") or ""))
    ]
    tg_digest_items = sum(len(d.get("items") or []) for d in tg_digests)
    tg_posts = [
        p for p in (tg.get("posts") or {}).values()
        if is_today(str(p.get("sent_at") or ""))
    ]

    vk_digests = [
        d for d in (vk.get("digests") or {}).values()
        if is_today(str(d.get("sent_at") or ""))
    ]
    vk_digest_items = sum(len(d.get("items") or []) for d in vk_digests)
    vk_posts = [
        p for p in (vk.get("posts") or {}).values()
        if is_today(str(p.get("sent_at") or ""))
    ]

    cat_today = []
    for row in catalogs.get("entries", []):
        raw = str(row.get("attempted_at") or row.get("submitted_at") or "")
        if is_today(raw):
            cat_today.append(row)

    promo_today = [
        row for row in tg_promo.get("entries", [])
        if is_today(str(row.get("attempted_at") or row.get("published_at") or ""))
    ]

    video_name = "Video — Generate & Publish (YouTube + TikTok + Instagram)"
    video_runs = [r for r in runs if r.get("name") == video_name and is_today(str(r.get("created_at") or ""))]
    video_latest = video_runs[0] if video_runs else None
    video_failures = sum(1 for r in video_runs if r.get("conclusion") == "failure")

    qa_runs = [r for r in runs if r.get("name") == "Checks — Full QA" and is_today(str(r.get("created_at") or ""))]
    qa_latest = qa_runs[0] if qa_runs else None
    qa_failures = sum(1 for r in qa_runs if r.get("conclusion") == "failure")

    lines = [
        f"📊 SpecAvto Control — отчёт за {today.strftime('%d.%m.%Y')}",
        "",
        "✅ Текущее состояние",
        f"• Сайт/деплой: {run_status(runs, 'Site — Build, Deploy & VK Publish')}",
        f"• Последний QA: {human_run_status(str((qa_latest or {}).get('conclusion') or (qa_latest or {}).get('status') or ''))}",
        f"• Новостей в базе: {len(news) if isinstance(news, list) else '—'}",
        "",
        "📰 Новости и соцсети",
        f"• News Fetch & Publish: {run_status(runs, 'News — Fetch & Publish')}",
        f"• Telegram: {len(tg_posts)} важных пост(а/ов) + {len(tg_digests)} дайджест(а/ов), {tg_digest_items} новостей в дайджестах",
        f"• VK: {len(vk_posts)} важных пост(а/ов) + {len(vk_digests)} дайджест(а/ов), {vk_digest_items} новостей в дайджестах",
        "",
        "🎬 Видео",
    ]

    if video_latest:
        latest_video_status = str(video_latest.get("conclusion") or video_latest.get("status") or "")
        lines.append(f"• Последний запуск: {human_run_status(latest_video_status)}")
        if latest_video_status == "success":
            lines.append("• YouTube + TikTok + Instagram: ✅ публикация завершена")
    else:
        lines.append("• Сегодня не запускался")

    lines += ["", "📚 Каталоги"]
    if cat_today:
        lines.extend(human_catalog_result(row) for row in cat_today)
        if not any(row.get("status") in {"submitted", "under_moderation", "published", "accepted"} for row in cat_today):
            lines.append("• Итог: нового автоматического размещения сегодня нет; неподходящие каталоги отсеяны.")
    else:
        lines.append("• Сегодня попыток не было")

    lines += ["", "📣 Telegram promotion"]
    lines.append(telegram_promo_summary(promo_today))

    lines += ["", "💰 Telegram Ads"]
    if ads.get("landing_url"):
        lines.append(f"• Посадочный пост готов: {ads.get('landing_url')}")
        lines.append("• Кампании подготовлены; запуск рекламы ждёт пополнения/настройки кабинета Telegram Ads")
    else:
        lines.append("• Посадочный пост не найден")

    lines += ["", "🧪 Стабильность"]
    latest_qa_status = str((qa_latest or {}).get("conclusion") or (qa_latest or {}).get("status") or "")
    if latest_qa_status == "success":
        lines.append("• ✅ Последняя полная проверка проекта прошла успешно")
    elif latest_qa_status:
        lines.append(f"• {human_run_status(latest_qa_status)} — последняя полная проверка проекта")
    else:
        lines.append("• Данных о последней полной проверке нет")

    report = "\n".join(lines)
    Path("/tmp/specavto-daily-report.txt").write_text(report + "\n", encoding="utf-8")

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print(report)
        print("TELEGRAM_BOT_TOKEN missing; report not sent.")
        return 0

    chat_id = resolve_control_chat_id(token)
    telegram_call(
        token,
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": report[:4000],
            "disable_web_page_preview": "true",
        },
    )
    print("DAILY_CONTROL_REPORT_SENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
