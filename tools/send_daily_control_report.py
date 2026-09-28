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


def site_analytics_lines(summary: dict[str, Any]) -> list[str]:
    """Whole-site traffic (Metrika) and Yandex search (Webmaster) block."""
    lines = ["", "🌐 Сайт целиком — последние 7 дней"]
    metrika = summary.get("metrika") or {}
    m_status = str(metrika.get("status") or "")
    if m_status == "ok":
        lines.append(
            f"• Всего визитов — {int(metrika.get('visits') or 0)}, "
            f"пользователей — {int(metrika.get('users') or 0)}"
        )
        for row in (metrika.get("sources") or [])[:5]:
            lines.append(f"• {row.get('name')}: {int(row.get('visits') or 0)} виз.")
    elif m_status == "missing_token":
        lines.append("• Общая посещаемость: нет токена Метрики")
    elif m_status == "error":
        lines.append(f"• ❌ Общая посещаемость не получена ({metrika.get('detail') or 'ошибка'})")
    else:
        lines.append("• Отчёт по общей посещаемости ещё не выполнялся")

    lines += ["", "🔎 Яндекс Поиск (Вебмастер)"]
    webmaster = summary.get("webmaster") or {}
    w_status = str(webmaster.get("status") or "")
    if w_status == "ok":
        index = webmaster.get("index") or {}
        problems = index.get("problems") or {}
        lines.append(
            f"• В поиске страниц — {int(index.get('searchable_pages') or 0)}, "
            f"исключено — {int(index.get('excluded_pages') or 0)}, ИКС — {int(index.get('sqi') or 0)}"
        )
        serious = int(problems.get("fatal") or 0) + int(problems.get("critical") or 0)
        if serious:
            lines.append(f"• ⚠️ Серьёзных проблем сайта в Вебмастере: {serious}")
        search = webmaster.get("search") or {}
        if search.get("status") == "error":
            lines.append(f"• ❌ Поисковые запросы не получены ({search.get('detail') or 'ошибка'})")
        elif "shows" in search:
            lines.append(
                f"• Показы — {int(search.get('shows') or 0)}, клики — {int(search.get('clicks') or 0)} "
                f"({search.get('date_from')} … {search.get('date_to')}, данные Вебмастера приходят с задержкой)"
            )
            for row in (search.get("top_queries") or [])[:5]:
                position = row.get("position")
                pos = f", поз. {position}" if position is not None else ""
                lines.append(
                    f"• «{row.get('query')}»: {int(row.get('shows') or 0)} пок., "
                    f"{int(row.get('clicks') or 0)} кл.{pos}"
                )
    elif w_status == "missing_token":
        lines.append("• Нет токена: нужен YANDEX_METRIKA_OAUTH_TOKEN с правом webmaster:hostinfo")
    elif w_status == "host_not_found":
        lines.append(f"• ❌ {webmaster.get('detail') or 'Сайт не найден в Вебмастере'}")
    elif w_status == "error":
        lines.append(f"• ❌ Данные Вебмастера не получены ({webmaster.get('detail') or 'ошибка'})")
        if webmaster.get("token_secret"):
            lines.append(f"• Использован секрет {webmaster.get('token_secret')}")
        if webmaster.get("hint"):
            lines.append(f"• {webmaster.get('hint')}")
    else:
        lines.append("• Отчёт Вебмастера ещё не выполнялся")
    return lines


def main() -> int:
    today = datetime.now(MSK).date()
    news = load_json(ROOT / "frontend/data/news.json", [])
    tg = load_json(ROOT / "frontend/data/telegram_state.json", {})
    vk = load_json(ROOT / "frontend/data/vk_state.json", {})
    catalogs = load_json(ROOT / "frontend/data/site_promo_history.json", {"entries": []})
    tg_promo = load_json(ROOT / "frontend/data/telegram_promo_history.json", {"entries": []})
    ads = load_json(ROOT / "frontend/data/telegram_ads_state.json", {})
    catalog_summary = load_json(ROOT / "frontend/data/daily_catalog_target.json", {})
    placement_summary = load_json(ROOT / "frontend/data/promotion/placement_verification_summary.json", {})
    editorial_summary = load_json(ROOT / "frontend/data/promotion/editorial_summary.json", {})
    editorial_history = load_json(ROOT / "frontend/data/promotion/editorial_history.json", {"entries": []})
    telegram_outreach = load_json(ROOT / "frontend/data/promotion/telegram_outreach_summary.json", {})
    manual_queue = load_json(ROOT / "frontend/data/promotion/manual_queue.json", {"entries": []})
    video_schedule = load_json(ROOT / "tools/autoposter/state/video_schedule.json", {"days": {}})
    traffic_summary = load_json(ROOT / "frontend/data/promotion/traffic_summary.json", {})
    site_analytics = load_json(ROOT / "frontend/data/promotion/site_analytics.json", {})

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
        f"• Telegram: обычных постов — {len(tg_posts)}, дайджестов — {len(tg_digests)}, новостей в дайджестах — {tg_digest_items}",
        f"• VK: обычных постов — {len(vk_posts)}, дайджестов — {len(vk_digests)}, новостей в дайджестах — {vk_digest_items}",
        "",
        "🎬 Видео",
    ]

    day_video = ((video_schedule.get("days") or {}).get(today.isoformat()) or {})
    lines.append(
        "• Утренний Shorts: "
        + ("✅ опубликован" if day_video.get("am") == "published" else "❌ не опубликован")
    )
    lines.append(
        "• Вечерний Shorts: "
        + ("✅ опубликован" if day_video.get("pm") == "published" else "❌ не опубликован")
    )
    if video_latest:
        latest_video_status = str(video_latest.get("conclusion") or video_latest.get("status") or "")
        lines.append(f"• Последний video-workflow: {human_run_status(latest_video_status)}")

    lines += ["", "📚 Каталоги"]
    if cat_today:
        lines.extend(human_catalog_result(row) for row in cat_today)
        if not any(row.get("status") in {"submitted", "under_moderation", "published", "accepted"} for row in cat_today):
            lines.append("• Итог: нового автоматического размещения сегодня нет; неподходящие каталоги отсеяны.")
    else:
        lines.append("• Сегодня попыток не было")

    lines += ["", "📣 Telegram promotion"]
    lines.append(telegram_promo_summary(promo_today))

    lines += ["", "📢 Продвижение — результат за день"]
    catalog_status = str(catalog_summary.get("status") or "")
    if catalog_status == "queue_exhausted":
        lines.append("• Новых размещений в каталогах: 0 — автоматическая очередь каталогов исчерпана")
    elif catalog_status in {"success", "already_successful_today"}:
        lines.append("• Каталоги: ✅ сегодня есть отправленная заявка/размещение")
    elif catalog_status:
        lines.append(f"• Каталоги: {catalog_status}")
    else:
        lines.append("• Каталоги: данных за сегодня нет")

    placement_states = placement_summary.get("states") or {}
    pending_count = int(placement_states.get("pending_review") or 0) + int(placement_states.get("still_pending") or 0)
    changed_count = int(placement_summary.get("changed") or 0)
    lines.append(f"• Проверка старых размещений: изменений — {changed_count}, всё ещё ждут — {pending_count}")

    editorial_status = str(editorial_summary.get("status") or "")
    if editorial_status == "nothing_planned":
        lines.append("• Отраслевые площадки: новых публикаций нет — подходящего автоматического действия сегодня не было")
    elif editorial_status == "email_prepared":
        target = str(editorial_summary.get("target_name") or "редакция")
        lines.append(f"• Отраслевые площадки: ✉️ подготовлено письмо для {target}")
    elif editorial_status:
        lines.append(f"• Отраслевые площадки: {editorial_status}")
    else:
        lines.append("• Отраслевые площадки: данных за сегодня нет")

    outreach_status = str(telegram_outreach.get("status") or "")
    if outreach_status == "no_bot_target":
        lines.append("• Telegram-реклама: новых автоматических контактов нет — доступные рекламные боты исчерпаны")
    elif outreach_status:
        lines.append(f"• Telegram-реклама: {outreach_status}")
    else:
        lines.append("• Telegram-реклама: данных за сегодня нет")

    pending_rows = [
        row for row in (manual_queue.get("entries") or [])
        if str(row.get("status") or "").lower() in {"ready", "pending", "todo"}
    ]
    pending_email = [row for row in pending_rows if row.get("channel") == "email"]
    pending_manual = [row for row in pending_rows if row.get("channel") != "email"]

    sent_email_today = [
        row for row in (editorial_history.get("entries") or [])
        if row.get("status") == "email_sent"
        and is_today(str(row.get("sent_at") or row.get("created_at") or ""))
    ]
    bounced_email_today = [
        row for row in (editorial_history.get("entries") or [])
        if row.get("status") in {"email_bounced", "email_invalid_domain"}
        and is_today(str(row.get("bounced_at") or row.get("delivery_checked_at") or row.get("sent_at") or row.get("created_at") or ""))
    ]
    lines.append(
        f"• Редакционные email: доставлены/ожидают ответа — {len(sent_email_today)}, "
        f"возвратов/невалидных адресов — {len(bounced_email_today)}, в очереди — {len(pending_email)}"
    )

    if pending_manual:
        lines.append(f"• Ручные задачи: {len(pending_manual)} — требуется ваше действие")
    else:
        lines.append("• Ручные задачи: 0")

    if (
        catalog_status == "queue_exhausted"
        and editorial_status == "nothing_planned"
        and outreach_status == "no_bot_target"
        and not pending_manual
        and not pending_email
    ):
        lines.append("• Итог: новых рекламных размещений за день — 0")
        lines.append("• Причина: текущий автоматический пул площадок исчерпан или временно недоступен; это не считается успешным продвижением.")

    lines += ["", "📈 Отдача рекламы — последние 7 дней"]
    traffic_status = str(traffic_summary.get("status") or "")
    traffic_sources = traffic_summary.get("sources") or []
    if traffic_status == "ok":
        totals = traffic_summary.get("totals") or {}
        lines.append(
            f"• UTM-трафик: визитов — {int(totals.get('visits') or 0)}, пользователей — {int(totals.get('users') or 0)}"
        )
        if traffic_sources:
            for row in traffic_sources[:5]:
                duration = int(row.get("avg_visit_duration_seconds") or 0)
                lines.append(
                    "• "
                    f"{row.get('source')}: {int(row.get('visits') or 0)} виз., "
                    f"{int(row.get('users') or 0)} чел., "
                    f"отказы {float(row.get('bounce_rate') or 0):.1f}%, "
                    f"глубина {float(row.get('page_depth') or 0):.1f}, "
                    f"время {duration} сек."
                )
        else:
            lines.append("• По рекламным UTM за период переходов пока не зафиксировано")
    elif traffic_status == "missing_token":
        lines.append("• Метрика считает посещения на сайте, но автоматическая выгрузка UTM ещё не подключена")
        lines.append("• Нужен один раз OAuth-токен Яндекс Метрики с правом metrika:read")
    elif traffic_status == "error":
        lines.append("• ❌ Не удалось получить рекламную статистику из Метрики")
    else:
        lines.append("• Автоматический UTM-отчёт ещё не выполнялся")

    lines += site_analytics_lines(site_analytics)

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

    if os.environ.get("CONTROL_TELEGRAM_ENABLED", "1").strip() == "0":
        print(report)
        print("CONTROL_TELEGRAM_DISABLED")
        return 0

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print(report)
        print("TELEGRAM_BOT_TOKEN missing; report not sent.")
        return 0

    try:
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
    except Exception as exc:
        print(report)
        print(f"DAILY_CONTROL_REPORT_TELEGRAM_FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
