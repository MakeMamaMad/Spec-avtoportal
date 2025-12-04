#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

NEWS_PATH = "frontend/data/news.json"


def load_current():
    with open(NEWS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_previous():
    """
    Берём предыдущую версию news.json из git (HEAD).
    Если её ещё не было — возвращаем пустой список.
    """
    try:
        raw = subprocess.check_output(
            ["git", "show", f"HEAD:{NEWS_PATH}"],
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []

    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        print("WARN: не удалось распарсить предыдущий news.json", file=sys.stderr)
        return []


def make_key(item):
    """
    Уникальный ключ новости, чтобы понять — новая она или нет.
    Пробуем по id/url/link, если нет — по title+source.
    """
    for key in ("id", "url", "link", "guid"):
        v = item.get(key)
        if v:
            return str(v)

    title = (item.get("title") or "").strip()
    src = item.get("source") or item.get("source_name") or ""
    return f"{title}::{src}"


def get_new_items(prev, current):
    # Специальный режим: TELEGRAM_FORCE_ALL=1 → считаем все новости новыми
    force_all = os.environ.get("TELEGRAM_FORCE_ALL") == "1"
    if force_all:
        print("TELEGRAM_FORCE_ALL=1 → считаем все новости новыми.", file=sys.stderr)
        prev_keys = set()
    else:
        prev_keys = {make_key(i) for i in prev}

    unique = [i for i in current if make_key(i) not in prev_keys]

    def get_date(it):
        for key in ("published_at", "published", "date", "created_at"):
            if key in it:
                return str(it[key])
        return ""

    # сортируем по дате, чтобы постить в нормальном порядке (от старых к новым)
    unique.sort(key=get_date)
    return unique


def build_text(item):
    title = item.get("title") or "(без заголовка)"
    src = item.get("source") or item.get("source_name") or ""

    rubrics = item.get("rubrics") or item.get("tags") or []
    if isinstance(rubrics, str):
        rubrics_list = [rubrics]
    elif isinstance(rubrics, list):
        rubrics_list = [str(x) for x in rubrics if x]
    else:
        rubrics_list = []

    line1 = f"📰 <b>{title}</b>"
    parts = [line1]

    if rubrics_list:
        parts.append("🏷 " + " · ".join(rubrics_list))

    if src:
        parts.append(f"🌐 {src}")

    # Ссылка: сначала пробуем на оригинал, потом на что вообще есть
    url = (
        item.get("canonical_url")
        or item.get("url")
        or item.get("link")
        or ""
    )

    if url:
        parts.append("")
        parts.append(url)

    text = "\n".join(parts)

    # ограничение Telegram — 4096 символов
    if len(text) > 4000:
        text = text[:3990] + "…"

    return text


def send_message(token: str, chat_id: str, text: str, disable_preview: bool = False):
    api_url = f"https://api.telegram.org/bot{token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true" if disable_preview else "false",
    }

    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(api_url, data=data)

    with urllib.request.urlopen(req, timeout=15) as resp:
        resp.read()  # главное, чтобы запрос прошёл


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print(
            "TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не заданы — пропускаем отправку.",
            file=sys.stderr,
        )
        return

    max_posts = int(os.environ.get("TELEGRAM_MAX_POSTS", "10"))

    try:
        current = load_current()
    except FileNotFoundError:
        print(f"{NEWS_PATH} не найден, нечего постить.", file=sys.stderr)
        return

    prev = load_previous()
    new_items = get_new_items(prev, current)

    if not new_items:
        print("Новых новостей для Telegram нет.", file=sys.stderr)
        return

    # берём только последние N, чтобы не заспамить канал
    new_items = new_items[-max_posts:]

    print(f"Отправляем в Telegram {len(new_items)} нов(ость/ости)...")

    errors = 0
    for item in new_items:
        title = (item.get("title") or "")[:80]
        print(f" → {title!r}")
        text = build_text(item)
        try:
            send_message(token, chat_id, text)
        except Exception as e:
            errors += 1
            print(f"Ошибка отправки в Telegram: {e}", file=sys.stderr)

    if errors:
        print(f"Готово, но с {errors} ошибк(ами).", file=sys.stderr)
    else:
        print("Готово, все сообщения отправлены.")


if __name__ == "__main__":
    main()
