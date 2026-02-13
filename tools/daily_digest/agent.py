import os
import json
import random
import html
from pathlib import Path
from datetime import datetime, timedelta, timezone

import requests
from dateutil import parser as dtparser


# --- ENV ---
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
NEWS_JSON_PATH = os.getenv("NEWS_JSON_PATH", "frontend/data/news.json").strip()

PICK_N = int(os.getenv("DIGEST_PICK_N", "5"))
LOOKBACK_HOURS = int(os.getenv("LOOKBACK_HOURS", "48"))

# am / pm (если пусто — определим автоматически)
DIGEST_SLOT = os.getenv("DIGEST_SLOT", "").strip().lower()

STATE_PATH = Path("tools/daily_digest/state.json")
STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

# Ключевые слова “строго тягачи/полуприцепы”
TOPIC_WORDS = [
    "полуприцеп", "полуприцепы", "прицеп", "прицепы", "тягач", "тягачи",
    "седельный", "седельные",
    "trailer", "trailers", "semi", "semi-trailer", "tractor trailer", "articulated",
]


def get_slot_utc() -> str:
    """Авто-определение слота по UTC. До 12:00 UTC = am, после = pm."""
    hour = datetime.now(timezone.utc).hour
    return "am" if hour < 12 else "pm"


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            s = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            s = {}
    else:
        s = {}

    s.setdefault("used_urls", [])
    # {"YYYY-MM-DD": {"am": true, "pm": true}}
    s.setdefault("last_post", {})
    return s


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def read_news() -> list[dict]:
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


def with_utm(url: str) -> str:
    if not url:
        return url
    if "utm_" in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}utm_source=telegram&utm_medium=digest&utm_campaign=daily"


def extract_title(item: dict) -> str:
    for k in ("title", "headline", "name"):
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def extract_date(item: dict) -> datetime | None:
    for k in ("published_at", "published", "date", "datetime", "time", "ts"):
        v = item.get(k)
        if not v:
            continue
        try:
            if isinstance(v, (int, float)):
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

    tags = item.get("tags") or item.get("categories")
    if isinstance(tags, list):
        joined = " ".join([str(x).lower() for x in tags])
        if any(w in joined for w in TOPIC_WORDS):
            return True

    return False



def pick_items(news: list[dict], used_urls: set[str]) -> list[dict]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=LOOKBACK_HOURS)

    fresh: list[tuple[int, dict]] = []
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
        score = 0
        if d:
            if d < cutoff:
                continue
            age_hours = (now - d).total_seconds() / 3600
            score = max(0, int(100 - age_hours))
        else:
            # если даты нет — низкий приоритет, но допускаем
            score = 10

        fresh.append((score, it))

    fresh.sort(key=lambda x: x[0], reverse=True)

    # берём верхнюю часть по “новизне”, а выбор внутри делаем рандомом
    top_pool = [it for _, it in fresh[: max(20, PICK_N * 4)]]

    if len(top_pool) <= PICK_N:
        return top_pool

    return random.sample(top_pool, PICK_N)


def esc_html(s: str) -> str:
    return html.escape(s, quote=False)


def meaning_for(title: str) -> str:
    t = (title or "").lower()

    if any(k in t for k in ["дешев", "подорож", "цена", "стоимост", "рынок", "продаж", "спрос"]):
        return ("Что это значит: возможны изменения цен на технику и запчасти. "
                "Если планируешь покупку/обновление — сравни предложения и сроки поставок.")

    if any(k in t for k in ["выпуск", "производств", "завод", "сократ", "рост выпуск", "серия"]):
        return ("Что это значит: при изменении производства могут меняться сроки поставок и наличие. "
                "Планируй обновление парка и заказы заранее.")

    if any(k in t for k in ["представ", "презент", "новинк", "модель", "выставк", "форум"]):
        return ("Что это значит: появляются новые комплектации и решения. "
                "Проверь, есть ли выгода по стоимости владения и сервису.")

    if any(k in t for k in ["штраф", "контроль", "инспекц", "требован", "закон", "правил", "сертиф"]):
        return ("Что это значит: повышается риск штрафов и простоев. "
                "Проверь документы, крепёж, свет/разъёмы и состояние узлов перед рейсом.")

    if any(k in t for k in ["ремонт", "сервис", "поломк", "неисправ", "тормоз", "ось", "подвеск", "шины"]):
        return ("Что это значит: обрати внимание на обслуживание узлов. "
                "Проблему дешевле поймать заранее, чем ловить простой на линии.")

    return "Что это значит: держи в фокусе влияние на эксплуатацию, сроки и затраты. Ссылки и детали — ниже."


def make_digest_post(items: list[dict], slot: str) -> str:
    today = datetime.now().strftime("%d.%m.%Y")

    if slot == "am":
        header = f"🚛 <b>Утренняя сводка по тягачам и полуприцепам — {today}</b>"
        footer = "📌 Утро: собрали главное и короткие выводы. Вечером — итоги дня."
    else:
        header = f"🚛 <b>Вечерняя сводка по тягачам и полуприцепам — {today}</b>"
        footer = "📌 Вечер: итоги дня"

    lines = [header, ""]

    for i, it in enumerate(items, 1):
        raw_title = extract_title(it)
        title = esc_html(raw_title)
        url = with_utm(extract_url(it))
        meaning = meaning_for(raw_title)

        lines.append(f"{i}️⃣ <b>{title}</b>")
        lines.append(esc_html(meaning))
        lines.append(f"🔗 {url}")
        lines.append("")

    lines.append(footer)
    return "\n".join(lines).strip()


def tg_send(text: str) -> None:
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

    # на случай ошибок — покажем ответ
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

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    slot = DIGEST_SLOT if DIGEST_SLOT in ("am", "pm") else get_slot_utc()

    posted_today = state.get("last_post", {}).get(today, {})
    if posted_today.get(slot):
        print(f"Digest already posted today for slot={slot}. Exit.")
        return

    used = set(state.get("used_urls", []))
    news = read_news()
    picked = pick_items(news, used)

    if not picked:
        print("No suitable items found (topic/freshness/duplicates). Exit.")
        return

    # минимум 3 пункта, иначе не постим “пустую” сводку
    if len(picked) < 3:
        print(f"Too few items for digest: {len(picked)}. Exit.")
        return

    post = make_digest_post(picked, slot)
    tg_send(post)

    # обновляем used_urls
    for it in picked:
        u = extract_url(it)
        if u:
            used.add(u)

    state["used_urls"] = list(used)[-500:]

    # отмечаем слот
    state.setdefault("last_post", {})
    state["last_post"].setdefault(today, {})
    state["last_post"][today][slot] = True

    # чистим историю last_post до 14 дней
    days = sorted(state["last_post"].keys())
    if len(days) > 14:
        for d in days[:-14]:
            state["last_post"].pop(d, None)

    save_state(state)
    print(f"OK: digest posted. slot={slot}")


if __name__ == "__main__":
    main()
