#!/usr/bin/env python3
"""Morning/evening Telegram digest for SpecAvtoPortal.

Uses the same baseline and state as the Telegram news publisher:
- only post-reboot, recent items are eligible;
- no importance rating is used;
- each digest randomly selects exactly three recent items when at least three are available;
- digested items are persisted in frontend/data/telegram_state.json.
"""
from __future__ import annotations

import html
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aggregator.telegram_visual import render_digest_card

NEWS_PATH = Path(os.getenv("NEWS_JSON_PATH", "frontend/data/news.json"))
STATE_PATH = Path("frontend/data/telegram_state.json")
CONFIG_PATH = Path("aggregator/telegram_config.json")

TAG_RE = re.compile(r"<[^>]+>")

CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("⚠️ Правила и контроль", ("гост", "тр тс", "закон", "регламент", "штраф", "тамож", "контроль")),
    ("📈 Рынок и производство", ("рынок", "цена", "продаж", "производств", "завод", "выпуск")),
    ("🚛 Техника", ("полуприцеп", "прицеп", "тягач", "грузовик", "шасси", "ось", "тормоз", "подвеск")),
    ("📦 Логистика", ("логист", "перевоз", "маршрут", "терминал", "склад", "порт", "контейнер")),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def strip_html(value: str) -> str:
    if not value:
        return ""
    text = str(value)
    text = re.sub(r"</(p|div|figure|li|h\d)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def clamp(text: str, max_len: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    cut = text[: max_len - 1].rsplit(" ", 1)[0].rstrip(" ,.;:-")
    return (cut or text[: max_len - 1]).rstrip() + "…"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except Exception as exc:
        print(f"WARN: cannot read {path}: {exc}", file=sys.stderr)
        return default


def load_config() -> dict[str, Any]:
    value = load_json(CONFIG_PATH, {})
    return value if isinstance(value, dict) else {}


def load_state() -> dict[str, Any]:
    state = load_json(STATE_PATH, {})
    if not isinstance(state, dict):
        state = {}
    state["schema"] = 2
    state.setdefault("welcome_message_id", None)
    state.setdefault("welcome_sent_at", None)
    state.setdefault("posts", {})
    state.setdefault("digested", {})
    state.setdefault("digests", {})
    for key in ("posts", "digested", "digests"):
        if not isinstance(state[key], dict):
            state[key] = {}
    return state


def save_state(state: dict[str, Any]) -> None:
    state["schema"] = 2
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(STATE_PATH)


def read_news() -> list[dict[str, Any]]:
    data = load_json(NEWS_PATH, [])
    if not isinstance(data, list):
        raise RuntimeError("news.json must be a list")
    return data


def load_baseline(config: dict[str, Any], current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ref = str(config.get("baseline_ref") or "").strip()
    if not ref:
        return current
    try:
        raw = subprocess.check_output(
            ["git", "show", f"{ref}:frontend/data/news.json"],
            stderr=subprocess.DEVNULL,
        )
        data = json.loads(raw.decode("utf-8"))
        if isinstance(data, list):
            return data
    except Exception as exc:
        print(f"WARN: cannot load digest baseline {ref}: {exc}", file=sys.stderr)
    return current


def make_key(item: dict[str, Any]) -> str:
    for key in ("canonical_url", "url", "link", "guid", "id"):
        value = item.get(key)
        if value:
            return str(value)
    return f"{str(item.get('title') or '').strip()}::{str(item.get('source') or '').strip()}"


def item_date(item: dict[str, Any]) -> str:
    for key in ("published_at", "published", "date", "created_at"):
        value = item.get(key)
        if value:
            return str(value)
    return ""


def parse_item_datetime(item: dict[str, Any]) -> datetime | None:
    raw = item_date(item).strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        pass
    try:
        parsed = parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def is_recent(item: dict[str, Any], max_age_hours: int) -> bool:
    published = parse_item_datetime(item)
    if published is None:
        return False
    seconds = (datetime.now(timezone.utc) - published).total_seconds()
    return -6 * 3600 <= seconds <= max_age_hours * 3600


def tags_for(item: dict[str, Any]) -> list[str]:
    raw = item.get("tags") or item.get("rubrics") or []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [str(tag).strip() for tag in raw if str(tag).strip()]


def category_for(item: dict[str, Any]) -> str:
    haystack = " ".join(
        [
            strip_html(str(item.get("title") or "")),
            strip_html(str(item.get("summary") or item.get("description") or "")),
            " ".join(tags_for(item)),
        ]
    ).lower()
    for label, needles in CATEGORY_RULES:
        if any(needle in haystack for needle in needles):
            return label
    return "🧩 Отрасль"


def build_site_url(site_base: str, item: dict[str, Any], slot: str) -> str:
    slug = str(item.get("slug") or "").strip()
    params = urllib.parse.urlencode(
        {
            "utm_source": "telegram",
            "utm_medium": "digest",
            "utm_campaign": f"{slot}_digest",
            "utm_content": slug or "news",
        }
    )
    if slug:
        return f"{site_base}news/{urllib.parse.quote(slug)}/?{params}"
    return f"{site_base}?{params}"


def choose_digest_items(
    baseline: list[dict[str, Any]],
    current: list[dict[str, Any]],
    state: dict[str, Any],
    *,
    max_age_hours: int,
    limit: int,
) -> list[dict[str, Any]]:
    baseline_keys = {make_key(item) for item in baseline}
    already_digested = set(state.get("digested", {}))

    eligible = [
        item
        for item in current
        if make_key(item) not in baseline_keys
        and is_recent(item, max_age_hours)
        and parse_item_datetime(item) is not None
    ]

    fresh = [item for item in eligible if make_key(item) not in already_digested]
    reused = [item for item in eligible if make_key(item) in already_digested]
    rng = random.SystemRandom()
    rng.shuffle(fresh)
    rng.shuffle(reused)
    return (fresh + reused)[:limit]

def digest_slot() -> str:
    forced = os.getenv("DIGEST_SLOT", "").strip().lower()
    if forced in {"am", "pm"}:
        return forced
    return "am" if datetime.now(timezone.utc).hour < 12 else "pm"


def digest_id(slot: str) -> str:
    return f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}:{slot}"


def make_digest_text(items: list[dict[str, Any]], slot: str, site_base: str) -> str:
    label = "Утренняя" if slot == "am" else "Вечерняя"
    today = datetime.now(timezone.utc).strftime("%d.%m.%Y")

    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(category_for(item), []).append(item)

    lines = [
        f"🚛 <b>{label} сводка СпецАвтоПортала · {today}</b>",
        f"<i>{len(items)} материалов, которые стоит знать</i>",
    ]

    order = [label for label, _ in CATEGORY_RULES] + ["🧩 Отрасль"]
    number = 0
    for category in order:
        category_items = grouped.get(category, [])
        if not category_items:
            continue
        lines.append("")
        lines.append(f"<b>{category}</b>")
        for item in category_items:
            number += 1
            title = html.escape(strip_html(str(item.get("title") or "Материал")))
            url = html.escape(build_site_url(site_base, item, slot), quote=True)
            lines.append(f'{number}. <a href="{url}"><b>{title}</b></a>')

    digest_link = site_base + "?" + urllib.parse.urlencode(
        {
            "utm_source": "telegram",
            "utm_medium": "digest",
            "utm_campaign": f"{slot}_digest",
            "utm_content": "footer",
        }
    )
    lines.extend(
        [
            "",
            f'🔗 <a href="{html.escape(digest_link, quote=True)}">Все новости на сайте</a>',
        ]
    )
    return clamp("\n".join(lines), 3900)


def send_message(token: str, chat_id: str, text: str, site_url: str) -> int:
    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
        "reply_markup": json.dumps(
            {
                "inline_keyboard": [
                    [{"text": "Открыть СпецАвтоПортал ↗", "url": site_url}],
                ]
            },
            ensure_ascii=False,
        ),
    }
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(api_url, data=data)
    with urllib.request.urlopen(req, timeout=20) as response:
        body = json.loads(response.read().decode("utf-8"))
    if not body.get("ok"):
        raise RuntimeError(body.get("description") or "Telegram sendMessage failed")
    message_id = (body.get("result") or {}).get("message_id")
    if not isinstance(message_id, int):
        raise RuntimeError("Telegram response does not contain message_id")
    return message_id


def build_digest_photo_caption(items: list[dict[str, Any]], slot: str, site_base: str) -> str:
    label = "Утренняя" if slot == "am" else "Вечерняя"
    lines = [
        f"<b>{label} сводка СпецАвтоПортала</b>",
        f"<i>{len(items)} материалов — главное к этому часу</i>",
        "",
    ]
    for index, item in enumerate(items[:5], 1):
        title = html.escape(clamp(strip_html(str(item.get("title") or "Материал")), 105))
        lines.append(f"{index}. {title}")
    lines.extend(["", "🔗 Все материалы — по кнопке ниже"])
    return "\n".join(lines)


def send_photo(
    token: str,
    chat_id: str,
    photo_path: Path,
    caption: str,
    site_url: str,
) -> int:
    api_url = f"https://api.telegram.org/bot{token}/sendPhoto"
    reply_markup = {
        "inline_keyboard": [
            [{"text": "Открыть СпецАвтоПортал ↗", "url": site_url}],
        ]
    }
    with photo_path.open("rb") as photo:
        response = requests.post(
            api_url,
            data={
                "chat_id": chat_id,
                "caption": caption,
                "parse_mode": "HTML",
                "reply_markup": json.dumps(reply_markup, ensure_ascii=False),
            },
            files={"photo": ("spec-avtoportal-digest.png", photo, "image/png")},
            timeout=30,
        )
    body = response.json()
    if not response.ok or not body.get("ok"):
        raise RuntimeError(body.get("description") or f"Telegram sendPhoto failed: {response.status_code}")
    message_id = (body.get("result") or {}).get("message_id")
    if not isinstance(message_id, int):
        raise RuntimeError("Telegram sendPhoto response does not contain message_id")
    return message_id


def send_digest_visual_or_fallback(
    token: str,
    chat_id: str,
    items: list[dict[str, Any]],
    slot: str,
    full_text: str,
    site_url: str,
    site_base: str,
) -> tuple[int, str]:
    try:
        with tempfile.TemporaryDirectory(prefix="specavto-digest-") as tmp_dir:
            card_path = Path(tmp_dir) / "digest.png"
            render_digest_card(slot, card_path)
            message_id = send_photo(
                token,
                chat_id,
                card_path,
                build_digest_photo_caption(items, slot, site_base),
                site_url,
            )
            return message_id, "visual"
    except Exception as exc:
        print(f"WARN: digest visual failed, text fallback: {exc}", file=sys.stderr)
        return send_message(token, chat_id, full_text, site_url), "text_fallback"


def main() -> int:
    config = load_config()
    if not config.get("enabled", False) or not config.get("digest_enabled", True):
        print("Telegram digest is disabled.")
        return 0

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

    state = load_state()
    slot = digest_slot()
    current_digest_id = digest_id(slot)
    if current_digest_id in state["digests"]:
        print(f"Digest already sent: {current_digest_id}")
        return 0

    current = read_news()
    baseline = load_baseline(config, current)
    items = choose_digest_items(
        baseline,
        current,
        state,
        max_age_hours=int(config.get("max_item_age_hours") or 48),
        limit=int(config.get("digest_items") or 5),
    )

    min_items = int(config.get("digest_min_items") or 2)
    if len(items) < min_items:
        print(f"Not enough recent items for digest: {len(items)} < {min_items}")
        return 0

    site_base = os.getenv("SITE_URL", "https://spec-avtoportal.ru/").rstrip("/") + "/"
    text = make_digest_text(items, slot, site_base)
    button_url = site_base + "?" + urllib.parse.urlencode(
        {
            "utm_source": "telegram",
            "utm_medium": "digest",
            "utm_campaign": f"{slot}_digest",
            "utm_content": "button",
        }
    )
    message_id, visual_mode = send_digest_visual_or_fallback(
        token,
        chat_id,
        items,
        slot,
        text,
        button_url,
        site_base,
    )

    sent_at = utc_now()
    state["digests"][current_digest_id] = {
        "message_id": message_id,
        "sent_at": sent_at,
        "slot": slot,
        "items": [make_key(item) for item in items],
        "visual": visual_mode,
    }
    for item in items:
        state["digested"][make_key(item)] = {
            "digest_id": current_digest_id,
            "message_id": message_id,
            "sent_at": sent_at,
            "title": str(item.get("title") or ""),
            "slug": str(item.get("slug") or ""),
        }

    # Keep digest history compact while preserving dedupe history for items.
    digest_keys = sorted(state["digests"].keys())
    for key in digest_keys[:-30]:
        state["digests"].pop(key, None)

    save_state(state)
    print(f"OK: digest posted slot={slot} message_id={message_id} items={len(items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
