import os
import json    
import random
import re
import html
from pathlib import Path
from datetime import datetime, timedelta, timezone

import requests
from dateutil import parser as dtparser


BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
NEWS_JSON_PATH = os.getenv("NEWS_JSON_PATH", "frontend/data/news.json").strip()
PICK_N = int(os.getenv("DIGEST_PICK_N", "6"))

STATE_PATH = Path("tools/daily_digest/state.json")
STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

# Ключевые слова “строго тягачи/полуприцепы”
TOPIC_WORDS = [
    "полуприцеп", "полуприцепы", "прицеп", "прицепы", "тягач", "тягачи",
    "седельный", "седельные",
    "trailer", "trailers", "semi", "semi-trailer", "tractor trailer", "articulated",
]

def load_state():
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"used_urls": [], "last_post_date": ""}

def save_state(state):
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

def read_news():
    p = Path(NEWS_JSON_PATH)
    if not p.exists():
        raise RuntimeError(f"news json not found: {NEWS_JSON_PATH}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise RuntimeError("news.json must be a list")
    return data

def extract_url(item: dict) -> str:
    for k in ("url", "link", "href", "source_url"):
        v = item.get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v.strip()
    return ""

def extract_title(item: dict) -> str:
    for k in ("title", "headline", "name"):
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""

def extract_date(item: dict) -> datetime | None:
    # Пытаемся найти дату в популярных полях
    for k in ("published_at", "published", "date", "datetime", "time", "ts"):
        v = item.get(k)
        if not v:
            continue
        try:
            if isinstance(v, (int, float)):
                # предполагаем unix seconds
                return datetime.fromtimestamp(float(v), tz=timezone.utc)
            if isinstance(v, str):
                d = dtparser.parse(v)
                if d.tzinfo is None:
                    d = d.replace(tzinfo=timezone.utc)
                return d
        except Exception:
            continue
    return None

def is_on_topic(item: dict) -> bool:
    title = extract_title(item).lower()
    if any(w in title for w in TOPIC_WORDS):
        return True
    # если есть теги/категории — тоже учитываем
    tags = item.get("tags") or item.get("categories")
    if isinstance(tags, list):
        joined = " ".join([str(x).lower() for x in tags])
        if any(w in joined for w in TOPIC_WORDS):
            return True
    return False

def pick_items(news: list[dict], used_urls: set[str]) -> list[dict]:
    # свежесть: последние 48 часов (можно увеличить)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=48)

    fresh = []
    for it in news:
        if not isinstance(it, dict):
            continue
        url = extract_url(it)
        title = extract_title(it)
        if not url or not title:
            continue
        if url in used_urls:
            continue
        if not is_on_topic(it):
            continue

        d = extract_date(it)
        # если даты нет — всё равно можно взять, но лучше ниже приоритет
        score = 0
        if d:
            if d < cutoff:
                continue
            # чем новее — тем выше шанс попасть
            age_hours = (now - d).total_seconds() / 3600
            score = max(0, int(100 - age_hours))
        else:
            score = 10

        fresh.append((score, it))

    # сортируем по “новизне”, но выбираем рандомом из верхней части
    fresh.sort(key=lambda x: x[0], reverse=True)
    top_pool = [it for _, it in fresh[: max(20, PICK_N * 4)]]

    if len(top_pool) <= PICK_N:
        return top_pool

    return random.sample(top_pool, PICK_N)

def esc_html(s: str) -> str:
    return html.escape(s, quote=False)

def make_digest_post(items: list[dict]) -> str:
    today = datetime.now().strftime("%d.%m.%Y")
    lines = [f"🚛 <b>Главное по тягачам и полуприцепам — {today}</b>", ""]

    for i, it in enumerate(items, 1):
        title = esc_html(extract_title(it))
        url = extract_url(it)

        meaning = "Что это значит: проверь влияние на цены, сроки поставок и эксплуатацию. Ссылки — ниже."

        lines.append(f"{i}️⃣ <b>{title}</b>")
        lines.append(esc_html(meaning))
        lines.append(f"🔗 {url}")
        lines.append("")

    lines.append("📌 Это ежедневная сводка: без спама, только важное + выводы.")
    return "\n".join(lines).strip()

def tg_send(text: str):
    if not BOT_TOKEN or not CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

    api = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    r = requests.post(api, json=payload, timeout=30)

    # Покажем телу ошибки Telegram (очень важно)
    try:
        j = r.json()
    except Exception:
        j = {"raw": r.text}

    print("Telegram status:", r.status_code)
    print("Telegram response:", j)

    r.raise_for_status()
    if not j.get("ok"):
        raise RuntimeError(f"Telegram API error: {j}")


def main():
    state = load_state()

    # защита от двойного постинга в один день (если workflow перезапустили)
    today = datetime.now().strftime("%Y-%m-%d")
    if state.get("last_post_date") == today:
        print("Digest already posted today. Exit.")
        return

    used = set(state.get("used_urls", []))
    news = read_news()
    picked = pick_items(news, used)

    if not picked:
        print("No suitable items found (topic/freshness/duplicates). Exit.")
        return

    post = make_digest_post(picked)
    tg_send(post)

    # обновляем state: запоминаем ссылки, чтобы завтра не повторяться
    for it in picked:
        url = extract_url(it)
        if url:
            used.add(url)

    state["used_urls"] = list(used)[-500:]  # ограничим память
    state["last_post_date"] = today
    save_state(state)

    print("OK: digest posted.")

if __name__ == "__main__":
    main()
