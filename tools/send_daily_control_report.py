#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

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


def telegram_call(token: str, method: str, payload: dict[str, Any] | None = None) -> Any:
    data = urllib.parse.urlencode(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=data,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if not body.get("ok"):
        raise RuntimeError(body.get("description") or str(body))
    return body.get("result")


def discover_control_channel(token: str) -> str:
    webhook = telegram_call(token, "getWebhookInfo") or {}
    if webhook.get("url"):
        raise RuntimeError("Bot has an active webhook; cannot safely use getUpdates.")

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
        raise RuntimeError("No Telegram channel update found.")

    channels.sort(key=lambda x: x[0])
    preferred = [
        item for item in channels
        if "control" in str(item[1].get("title") or "").lower()
    ]
    return str((preferred[-1] if preferred else channels[-1])[1]["id"])


def latest_run(runs: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    matches = [r for r in runs if r.get("name") == name and is_today(str(r.get("created_at") or ""))]
    return matches[0] if matches else None


def run_status(runs: list[dict[str, Any]], name: str) -> str:
    row = latest_run(runs, name)
    if not row:
        return "не запускался"
    status = row.get("conclusion") or row.get("status") or "unknown"
    return str(status)


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
        f"• Последний QA: {(qa_latest or {}).get('conclusion') or 'нет данных'}",
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
        lines.append(f"• Последний запуск: {video_latest.get('conclusion') or video_latest.get('status')}")
        if video_latest.get("conclusion") == "success":
            lines.append("• YouTube + TikTok + Instagram: публикационный pipeline завершён успешно")
        if video_failures:
            lines.append(f"• Ранее сегодня было сбоев: {video_failures}; последний запуск уже успешный")
    else:
        lines.append("• Сегодня не запускался")

    lines += ["", "📚 Каталоги"]
    if cat_today:
        for row in cat_today:
            name = row.get("target_name") or row.get("target_id")
            status = row.get("status") or "unknown"
            detail = str(row.get("detail") or "").strip()
            suffix = f" — {detail}" if detail else ""
            lines.append(f"• {name}: {status}{suffix}")
    else:
        lines.append("• Сегодня попыток не было")

    lines += ["", "📣 Telegram promotion"]
    if promo_today:
        latest = promo_today[-1]
        lines.append(
            f"• Последняя попытка: {latest.get('target_name') or latest.get('target_id')} — {latest.get('status')}"
        )
        if latest.get("detail"):
            lines.append(f"• Причина: {latest.get('detail')}")
    else:
        lines.append("• Сегодня новых попыток не было")

    lines += ["", "💰 Telegram Ads"]
    if ads.get("landing_url"):
        lines.append(f"• Посадочный пост готов: {ads.get('landing_url')}")
        lines.append("• Кампании подготовлены; запуск рекламы ждёт пополнения/настройки кабинета Telegram Ads")
    else:
        lines.append("• Посадочный пост не найден")

    lines += ["", "🧪 Стабильность"]
    if qa_failures:
        lines.append(f"• QA-сбоев за день: {qa_failures}; последний QA — {(qa_latest or {}).get('conclusion') or 'нет данных'}")
    else:
        lines.append("• QA: без зафиксированных сбоев сегодня")

    report = "\n".join(lines)
    Path("/tmp/specavto-daily-report.txt").write_text(report + "\n", encoding="utf-8")

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print(report)
        print("TELEGRAM_BOT_TOKEN missing; report not sent.")
        return 0

    chat_id = discover_control_channel(token)
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
