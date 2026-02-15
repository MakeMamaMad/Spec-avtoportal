import os
import json
import random
import html
from pathlib import Path
from datetime import datetime, timezone

import requests
from dateutil import parser as dtparser


# --- ENV ---
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
NEWS_JSON_PATH = os.getenv("NEWS_JSON_PATH", "frontend/data/news.json").strip()

# Сколько новостей в дайджесте (3–5). По умолчанию 5.
PICK_N = int(os.getenv("DIGEST_PICK_N", "5"))

# am / pm (если пусто — определим автоматически)
DIGEST_SLOT = os.getenv("DIGEST_SLOT", "").strip().lower()

STATE_PATH = Path("tools/daily_digest/state.json")
STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

# Мягкий бан-лист "мусора"
BLOCK_WORDS = ["porsche", "lamborghini", "audi", "кроссовер", "внедорожник", "iphone", "смартфон"]


# ----------------------------
# Классификация + "что это значит"
# ----------------------------
def classify(title: str, url: str = "") -> str:
    t = (title or "").lower()
    u = (url or "").lower()

    if any(k in t for k in ["штраф", "оштраф", "провер", "контроль", "закон", "регламент", "гост", "сертиф", "еврокомисс", "санкц"]):
        return "rules"
    if any(k in t for k in ["цена", "подорож", "дешев", "рынок", "спрос", "продаж", "пошлин", "инфляц"]):
        return "market"
    if any(k in t for k in ["завод", "выпуск", "производств", "поставка", "дефицит", "логистик", "склад", "импорт", "экспорт"]):
        return "supply"
    if any(k in t for k in ["тягач", "полуприцеп", "прицеп", "грузовик", "фура", "шасси", "ось", "тормоз", "подвеск", "шины", "ремонт", "сервис"]):
        return "ops"
    if any(k in t for k in ["dhl", "logistics", "перевоз", "транспорт", "контейнер", "интермодал", "терминал", "порт", "склад"]):
        return "logistics"

    # Иногда полезно отсечь совсем "не про транспорт", но ты просил всегда активность,
    # поэтому просто помечаем как other.
    return "other"


MEANING_BANK = {
    "rules": [
        "Что это значит: выше риск проверок и штрафов. Держи в порядке документы, свет/разъёмы, крепёж и узлы перед рейсом.",
        "Что это значит: возможны новые требования. Проверь регламенты и подготовь технику/документы заранее, чтобы не ловить простой.",
    ],
    "market": [
        "Что это значит: может измениться стоимость владения. Если планируешь покупку/обновление — сравни цены и условия, заложи запас по бюджету.",
        "Что это значит: рынок качает. Проверь влияние на цену техники/запчастей и сроки поставок.",
    ],
    "supply": [
        "Что это значит: возможны сдвиги по срокам и наличию. Планируй закупки и ремонт заранее, особенно расходники.",
        "Что это значит: цепочки поставок могут меняться. Держи альтернативы по брендам и узлам, уточняй сроки у поставщиков.",
    ],
    "ops": [
        "Что это значит: напрямую про эксплуатацию. Проверь узлы и регламент ТО, чтобы не попасть на простой в рейсе.",
        "Что это значит: часть проблем можно предупредить заранее. Лучше найти риск до выхода на линию.",
    ],
    "logistics": [
        "Что это значит: могут поменяться условия перевозок/маршрутов. Это влияет на сроки и расходы на рейс.",
        "Что это значит: возможна перестройка логистики. Держи в уме альтернативные маршруты и окна доставки.",
    ],
    "other": [
        "Что это значит: новость смежная. Оцени влияние на перевозки/рынок техники, иначе можно пропускать.",
        "Что это значит: влияние неочевидно. Смотри только если затрагивает транспорт, логистику или рынок техники.",
    ],
}


def meaning_for(title: str, url: str = "") -> str:
    c = classify(title, url)
    return random.choice(MEANING_BANK.get(c, MEANING_BANK["other"]))


# ----------------------------
# State / helpers
# ----------------------------
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


def extract_date(item: dict):
    """Не обязательно используется, но пусть будет на будущее."""
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


def esc_html(s: str) -> str:
    return html.escape(s or "", quote=False)


# ----------------------------
# Picking (always 3–5, no topic)
# ----------------------------
def pick_items(news: list[dict], used_urls: set[str]) -> list[dict]:
    """
    Всегда стараемся выбрать PICK_N новостей без темы.
    1) Сначала берём "новые" (не в used_urls) и не из BLOCK_WORDS
    2) Если таких < 3 — разрешаем повтор (иначе канал умрёт), но всё равно баним BLOCK_WORDS
    """
    candidates: list[dict] = []

    for it in news:
        if not isinstance(it, dict):
            continue
        url = extract_url(it)
        title = extract_title(it)
        if not url or not title:
            continue

        title_l = title.lower()
        if any(w in title_l for w in BLOCK_WORDS):
            continue

        if url in used_urls:
            continue

        candidates.append(it)

    # Если всё "съедено" used_urls — разрешаем повтор, но без мусора
    if len(candidates) < 3:
        candidates = []
        for it in news:
            if not isinstance(it, dict):
                continue
            url = extract_url(it)
            title = extract_title(it)
            if not url or not title:
                continue

            title_l = title.lower()
            if any(w in title_l for w in BLOCK_WORDS):
                continue

            candidates.append(it)

    if not candidates:
        return []

    n = min(PICK_N, len(candidates))

    if len(candidates) <= n:
        return candidates

    return random.sample(candidates, n)


# ----------------------------
# Digest formatting (grouped)
# ----------------------------
def make_digest_post(items: list[dict], slot: str) -> str:
    today = datetime.now().strftime("%d.%m.%Y")
    header = (
        f"🚛 <b>{'Утренняя' if slot=='am' else 'Вечерняя'} сводка — {today}</b>\n"
        f"<i>{len(items)} новостей + короткий вывод по каждой</i>\n"
    )

    groups = {"rules": [], "market": [], "supply": [], "ops": [], "logistics": [], "other": []}
    for it in items:
        title = extract_title(it)
        url = with_utm(extract_url(it))
        c = classify(title, url)
        groups[c].append((title, url))

    order = [
        ("rules", "⚠️ Контроль / правила"),
        ("market", "📈 Рынок / цены"),
        ("supply", "🚚 Поставки / производство"),
        ("ops", "🔧 Эксплуатация / техника"),
        ("logistics", "📦 Логистика"),
        ("other", "🧩 Остальное"),
    ]

    lines = [header]
    n = 0

    for key, label in order:
        if not groups[key]:
            continue
        lines.append(f"\n<b>{label}</b>")
        for title, url in groups[key]:
            n += 1
            m = meaning_for(title, url)
            lines.append(f"{n}️⃣ <b>{esc_html(title)}</b>")
            lines.append(esc_html(m))
            lines.append(f"🔗 {url}")

    lines.append("\n📌 <b>Сайт</b> — архив и подборка. <b>TG</b> — 2 сводки в день + лента новостей.")
    return "\n".join(lines).strip()


# ----------------------------
# Telegram send
# ----------------------------
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

    try:
        j = r.json()
    except Exception:
        j = {"raw": r.text}

    print("Telegram status:", r.status_code)
    print("Telegram response:", j)

    r.raise_for_status()
    if not j.get("ok"):
        raise RuntimeError(f"Telegram API error: {j}")


# ----------------------------
# Main
# ----------------------------
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
        print("No suitable items found. Exit.")
        return

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

    state["used_urls"] = list(used)[-800:]  # чуть больше памяти

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
