#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from telegram_control import resolve_control_chat_id, telegram_call

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "frontend/data/news.json"
LOG_PATH = Path("/tmp/control-source-run.log")
JOBS_PATH = Path("/tmp/control-source-jobs.json")


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def news_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("items", "news", "entries"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def news_key(row: dict[str, Any]) -> str:
    for key in ("id", "slug", "url", "link"):
        value = str(row.get(key) or "").strip()
        if value:
            return key + ":" + value
    return "fallback:" + "|".join(
        [
            str(row.get("title") or "").strip(),
            str(row.get("published_at") or row.get("date") or "").strip(),
        ]
    )


def old_news_from_git(head_sha: str) -> list[dict[str, Any]]:
    if not head_sha:
        return []
    proc = subprocess.run(
        ["git", "show", f"{head_sha}:frontend/data/news.json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return []
    try:
        return news_items(json.loads(proc.stdout))
    except Exception:
        return []


def build_news_message(conclusion: str, head_sha: str) -> str:
    if conclusion != "success":
        return (
            "📰 Новости — прогон каждые 3 часа\n"
            "❌ Обновление завершилось с ошибкой. Новые новости на сайте этим прогоном не подтверждены."
        )

    current = news_items(load_json(NEWS_PATH, []))
    old = old_news_from_git(head_sha)
    old_keys = {news_key(row) for row in old}
    added = [row for row in current if news_key(row) not in old_keys]

    if added:
        return (
            "📰 Новости — прогон каждые 3 часа\n"
            f"✅ На сайт добавлено новых новостей: {len(added)}.\n"
            f"Всего новостей в базе: {len(current)}."
        )
    return (
        "📰 Новости — прогон каждые 3 часа\n"
        "ℹ️ Новых новостей в этом прогоне не найдено.\n"
        f"Всего новостей в базе: {len(current)}."
    )


def source_jobs() -> list[dict[str, Any]]:
    payload = load_json(JOBS_PATH, {})
    jobs = payload.get("jobs") if isinstance(payload, dict) else None
    return [row for row in (jobs or []) if isinstance(row, dict)]


def build_video_message(conclusion: str) -> str | None:
    jobs = source_jobs()
    publish_jobs = [
        row
        for row in jobs
        if "publish" in str(row.get("name") or "").lower()
        and "gate" not in str(row.get("name") or "").lower()
    ]
    if not publish_jobs:
        return None

    job = publish_jobs[-1]
    job_conclusion = str(job.get("conclusion") or "").lower()
    if job_conclusion == "skipped":
        return None
    if conclusion == "success" and job_conclusion == "success":
        return (
            "🎬 Ролики\n"
            "✅ Новый ролик опубликован в YouTube Shorts, TikTok и Instagram Reels."
        )
    return (
        "🎬 Ролики\n"
        "❌ Публикация нового ролика в соцсети не завершилась успешно. Нужна проверка video-workflow."
    )


def source_log() -> str:
    try:
        return LOG_PATH.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def parse_last_sent(log: str) -> dict[str, Any] | None:
    matches = re.findall(r"DAILY_EDITORIAL_EMAIL_SENT\s+(\{.*?\})(?:\r?\n|$)", log)
    for raw in reversed(matches):
        try:
            value = json.loads(raw)
            if isinstance(value, dict):
                return value
        except Exception:
            continue
    return None


def build_bounce_message(conclusion: str) -> str | None:
    log = source_log()
    errors = re.findall(r"GMAIL_BOUNCE_CHECK_ERROR\s+(\{.*?\})(?:\r?\n|$)", log)
    if errors:
        try:
            error = json.loads(errors[-1])
        except Exception:
            error = {}
        streak = int(error.get("streak") or 1)
        # First failure, then once a day while the same problem persists.
        if streak != 1 and streak % 24 != 0:
            return None
        lines = ["✉️ Реклама — Gmail", "❌ Проверка доставки Gmail завершилась ошибкой."]
        if error.get("hint"):
            lines.append(str(error["hint"]))
        if error.get("code"):
            lines.append(f"Код: {error['code']}" + (f" (подряд: {streak})" if streak > 1 else ""))
        return "\n".join(lines)

    matches = re.findall(r"GMAIL_BOUNCE_CHECK_OK\s+(\{.*?\})(?:\r?\n|$)", log)
    if not matches:
        if conclusion != "success":
            return (
                "✉️ Реклама — Gmail\n"
                "❌ Проверка доставки Gmail завершилась ошибкой."
            )
        return None

    try:
        payload = json.loads(matches[-1])
    except Exception:
        return None

    changes = payload.get("changes") or []
    if not changes:
        return None

    lines = ["✉️ Реклама — Gmail", "❌ Обнаружены недоставленные письма:"]
    for row in changes[:8]:
        name = str(row.get("target_name") or row.get("target_id") or "редакция")
        recipients = ", ".join(str(x) for x in (row.get("bounced_recipients") or []))
        lines.append(f"• {name}: {recipients or 'адрес вернул письмо'}")
    lines.append("Плохие адреса автоматически исключены из дальнейшей рассылки.")
    return "\n".join(lines)


def build_sdelanounas_message(conclusion: str) -> str | None:
    log = source_log()

    if "SDELANOUNAS_DAILY_SKIP already_posted_today" in log:
        return None
    if "SDELANOUNAS_DAILY_NO_TARGET" in log:
        return (
            "📣 Реклама — Сделано у нас\n"
            "⚪ Сегодня подходящей новости для публикации не найдено."
        )

    published_matches = re.findall(
        r"SDELANOUNAS_PUBLISHED\s+(\{.*?\})(?:\r?\n|$)",
        log,
    )
    if published_matches:
        try:
            payload = json.loads(published_matches[-1])
        except Exception:
            payload = {}
        title = str(payload.get("title") or "материал")
        url = str(payload.get("public_url") or "")
        lines = [
            "📣 Реклама — Сделано у нас",
            f"✅ Опубликовано: {title}",
        ]
        if url:
            lines.append(url)
        return "\n".join(lines)

    result_matches = re.findall(
        r"SDELANOUNAS_RESULT=(\{.*?\})(?:\r?\n|$)",
        log,
    )
    if result_matches:
        try:
            payload = json.loads(result_matches[-1])
        except Exception:
            payload = {}
        title = str(payload.get("title") or "материал")
        return (
            "📣 Реклама — Сделано у нас\n"
            f"⏳ Материал отправлен: {title}. Публичное появление ещё проверяется."
        )

    if conclusion != "success":
        return (
            "📣 Реклама — Сделано у нас\n"
            "❌ Ежедневная публикация завершилась ошибкой."
        )
    return None


def build_email_message(conclusion: str) -> str | None:
    log = source_log()
    sent = parse_last_sent(log)
    rejected = len(re.findall(r"DAILY_EDITORIAL_EMAIL_REJECT\b", log))

    if sent:
        name = str(sent.get("target_name") or sent.get("target_id") or "редакция")
        recipients = sent.get("recipients") or []
        recipient_text = ", ".join(str(x) for x in recipients if str(x).strip())
        lines = [
            "✉️ Реклама — Gmail",
            f"✅ Gmail принял письмо к отправке: {name}.",
        ]
        if recipient_text:
            lines.append(f"Адрес: {recipient_text}.")
        if rejected:
            lines.append(f"До рабочего адреса отсеяно невалидных кандидатов: {rejected}.")
        if conclusion != "success":
            lines.append("⚠️ Сам workflow затем завершился технической ошибкой, но Gmail уже принял письмо.")
        return "\n".join(lines)

    if "DAILY_EDITORIAL_EMAIL_SKIP already_sent_today" in log:
        return None
    if "DAILY_EDITORIAL_EMAIL_NO_TARGET" in log:
        return (
            "✉️ Реклама — Gmail\n"
            "⚪ Сегодня новый рабочий email-контакт не найден, письмо не отправлено."
        )
    if "DAILY_EDITORIAL_EMAIL_EXHAUSTED" in log:
        return (
            "✉️ Реклама — Gmail\n"
            f"⚪ Письмо не отправлено: проверены кандидаты, рабочего адреса не найдено. Отсеяно: {rejected}."
        )
    if conclusion != "success":
        return (
            "✉️ Реклама — Gmail\n"
            "❌ Ежедневная email-реклама завершилась ошибкой до подтверждённой отправки."
        )
    return None


def build_message() -> str | None:
    workflow = os.environ.get("SOURCE_WORKFLOW_NAME", "").strip()
    conclusion = os.environ.get("SOURCE_WORKFLOW_CONCLUSION", "").strip().lower()
    head_sha = os.environ.get("SOURCE_HEAD_SHA", "").strip()

    if workflow == "News — Fetch & Publish":
        return build_news_message(conclusion, head_sha)
    if workflow == "Video — Generate & Publish (YouTube + TikTok + Instagram)":
        return build_video_message(conclusion)
    if workflow == "Promotion — Editorial Placement":
        return build_email_message(conclusion)
    if workflow == "Promotion — Gmail Delivery Check":
        return build_bounce_message(conclusion)
    if workflow == "Promotion — SdelanoU nas Daily":
        return build_sdelanounas_message(conclusion)
    return None


def main() -> int:
    message = build_message()
    if not message:
        print("FILTERED_CONTROL_SKIP")
        return 0

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

    chat_id = resolve_control_chat_id(token)
    telegram_call(
        token,
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": "true",
        },
    )
    print("FILTERED_CONTROL_SENT")
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
