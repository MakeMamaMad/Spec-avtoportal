#!/usr/bin/env python3
"""Editorial Telegram publisher for SpecAvtoPortal.

Rules:
- archive items that existed before the reboot baseline are never published;
- recent new items are published without importance scoring;
- morning/evening digests are selected independently from recent items;
- a shared state prevents duplicates between immediate posts and digests;
- every successful Telegram message_id is persisted.
"""
from __future__ import annotations

import html as html_lib
import json
import os
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

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from telegram_visual import render_important_card

NEWS_PATH = Path("frontend/data/news.json")
STATE_PATH = Path("frontend/data/telegram_state.json")
CONFIG_PATH = Path("aggregator/telegram_config.json")

TAG_RE = re.compile(r"<[^>]+>")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def strip_html(value: str) -> str:
    if not value:
        return ""
    text = str(value)
    text = re.sub(r"</(p|div|figure|li|h\d)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = TAG_RE.sub(" ", text)
    text = html_lib.unescape(text)
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
    config = load_json(CONFIG_PATH, {})
    return config if isinstance(config, dict) else {}


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

    if not isinstance(state["posts"], dict):
        state["posts"] = {}
    if not isinstance(state["digested"], dict):
        state["digested"] = {}
    if not isinstance(state["digests"], dict):
        state["digests"] = {}
    return state


def save_state(state: dict[str, Any]) -> None:
    state["schema"] = 2
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(STATE_PATH)


def load_current() -> list[dict[str, Any]]:
    data = load_json(NEWS_PATH, [])
    return data if isinstance(data, list) else []


def load_baseline(
    config: dict[str, Any],
    current: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Load the frozen pre-reset news snapshot.

    Fail closed: if the baseline cannot be loaded, use current items as the
    baseline so the bot never floods the channel with archive content.
    """
    ref = str(config.get("baseline_ref") or "").strip()
    if not ref:
        print("WARN: Telegram baseline_ref is empty; publishing is blocked.", file=sys.stderr)
        return current

    try:
        raw = subprocess.check_output(
            ["git", "show", f"{ref}:{NEWS_PATH.as_posix()}"],
            stderr=subprocess.DEVNULL,
        )
        data = json.loads(raw.decode("utf-8"))
        if isinstance(data, list):
            return data
    except Exception as exc:
        print(f"WARN: cannot load Telegram baseline {ref}: {exc}", file=sys.stderr)

    return current


def make_key(item: dict[str, Any]) -> str:
    for key in ("canonical_url", "url", "link", "guid", "id"):
        value = item.get(key)
        if value:
            return str(value)

    title = str(item.get("title") or "").strip()
    source = str(item.get("source") or item.get("source_name") or "").strip()
    return f"{title}::{source}"


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
        value = raw.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(value)
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
    age = datetime.now(timezone.utc) - published
    return age.total_seconds() >= -6 * 3600 and age.total_seconds() <= max_age_hours * 3600


def tags_for(item: dict[str, Any]) -> list[str]:
    raw = item.get("tags") or item.get("rubrics") or []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [str(tag).strip() for tag in raw if str(tag).strip()]


def get_unhandled_items(
    baseline: list[dict[str, Any]],
    current: list[dict[str, Any]],
    state: dict[str, Any],
) -> list[dict[str, Any]]:
    baseline_keys = {make_key(item) for item in baseline}
    posted_keys = set(state.get("posts", {}).keys())

    queue = [
        item
        for item in current
        if make_key(item) not in baseline_keys
        and make_key(item) not in posted_keys
    ]
    queue.sort(key=item_date)
    return queue


def build_site_url(
    site_base: str,
    item: dict[str, Any],
    idx: int | None = None,
    *,
    medium: str = "social",
    campaign: str = "news",
    content: str = "",
) -> str:
    slug = str(item.get("slug") or "").strip()
    params = {
        "utm_source": "telegram",
        "utm_medium": medium,
        "utm_campaign": campaign,
    }
    if content or slug:
        params["utm_content"] = content or slug

    if slug:
        return f"{site_base}news/{urllib.parse.quote(slug)}/?{urllib.parse.urlencode(params)}"

    if isinstance(idx, int):
        params["i"] = idx
        return f"{site_base}article.html?{urllib.parse.urlencode(params)}"
    return site_base + "?" + urllib.parse.urlencode(params)


def display_source(item: dict[str, Any]) -> str:
    source = str(item.get("source_name") or item.get("source") or "").strip()
    if source.lower() in {"", "source", "rss", "feed"}:
        source = str(item.get("domain") or "").replace("www.", "").strip()
    return source


def build_text(item: dict[str, Any], site_url: str) -> str:
    title = html_lib.escape(str(item.get("title") or "(без заголовка)").strip())
    source = html_lib.escape(display_source(item))
    summary = html_lib.escape(
        clamp(
            strip_html(str(item.get("summary") or item.get("description") or "")),
            430,
        )
    )

    visible_tags = [
        html_lib.escape(tag)
        for tag in tags_for(item)
        if tag.lower() not in {"новости", "partner", "партнёр"}
    ][:3]

    original_url = str(
        item.get("canonical_url")
        or item.get("url")
        or item.get("link")
        or ""
    ).strip()

    parts = ["📰 <b>СпецАвтоПортал</b>", f"<b>{title}</b>"]
    if summary:
        parts.append(summary)
    if visible_tags:
        parts.append("🏷 " + " · ".join(visible_tags))
    if source:
        parts.append(f"🌐 {source}")

    safe_site = html_lib.escape(site_url, quote=True)
    parts.append("")
    parts.append(f'🔗 <a href="{safe_site}">Разобраться на СпецАвтоПортале</a>')

    if original_url:
        safe_original = html_lib.escape(original_url, quote=True)
        parts.append(f'<a href="{safe_original}">Первоисточник ↗</a>')

    return clamp("\n".join(parts), 3900)


def api_call(token: str, method: str, payload: dict[str, Any]) -> dict[str, Any]:
    api_url = f"https://api.telegram.org/bot{token}/{method}"
    encoded: dict[str, str] = {}
    for key, value in payload.items():
        if isinstance(value, (dict, list)):
            encoded[key] = json.dumps(value, ensure_ascii=False)
        elif isinstance(value, bool):
            encoded[key] = "true" if value else "false"
        else:
            encoded[key] = str(value)

    data = urllib.parse.urlencode(encoded).encode("utf-8")
    req = urllib.request.Request(api_url, data=data)

    with urllib.request.urlopen(req, timeout=20) as response:
        body = json.loads(response.read().decode("utf-8"))

    if not body.get("ok"):
        raise RuntimeError(body.get("description") or f"Telegram {method} failed")
    result = body.get("result")
    return result if isinstance(result, dict) else {"result": result}


def send_message(
    token: str,
    chat_id: str,
    text: str,
    *,
    site_url: str = "",
    disable_preview: bool = False,
) -> int:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": disable_preview,
    }
    if site_url:
        payload["reply_markup"] = {
            "inline_keyboard": [
                [{"text": "Читать на сайте ↗", "url": site_url}],
            ]
        }

    result = api_call(token, "sendMessage", payload)
    message_id = result.get("message_id")
    if not isinstance(message_id, int):
        raise RuntimeError("Telegram response does not contain message_id")
    return message_id


def build_photo_caption(item: dict[str, Any], site_url: str) -> str:
    title = html_lib.escape(clamp(strip_html(str(item.get("title") or "Важная новость")), 180))
    summary = html_lib.escape(
        clamp(strip_html(str(item.get("summary") or item.get("description") or "")), 430)
    )
    source = html_lib.escape(display_source(item))
    safe_site = html_lib.escape(site_url, quote=True)

    parts = [f"<b>{title}</b>"]
    if summary:
        parts.append(summary)
    if source:
        parts.append(f"🌐 {source}")
    parts.append(f'🔗 <a href="{safe_site}">Читать на СпецАвтоПортале</a>')
    caption = "\n\n".join(parts)
    return caption[:1000]


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
            [{"text": "Читать на сайте ↗", "url": site_url}],
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
            files={"photo": ("spec-avtoportal.png", photo, "image/png")},
            timeout=30,
        )
    body = response.json()
    if not response.ok or not body.get("ok"):
        raise RuntimeError(body.get("description") or f"Telegram sendPhoto failed: {response.status_code}")
    message_id = (body.get("result") or {}).get("message_id")
    if not isinstance(message_id, int):
        raise RuntimeError("Telegram sendPhoto response does not contain message_id")
    return message_id


def send_visual_or_fallback(
    token: str,
    chat_id: str,
    item: dict[str, Any],
    text: str,
    site_url: str,
    disable_preview: bool,
) -> tuple[int, str]:
    try:
        with tempfile.TemporaryDirectory(prefix="specavto-tg-") as tmp_dir:
            card_path = Path(tmp_dir) / "important.png"
            render_important_card(item, card_path)
            message_id = send_photo(
                token,
                chat_id,
                card_path,
                build_photo_caption(item, site_url),
                site_url,
            )
            return message_id, "visual"
    except Exception as exc:
        print(f"WARN: Telegram visual failed, text fallback: {exc}", file=sys.stderr)
        message_id = send_message(
            token,
            chat_id,
            text,
            site_url=site_url,
            disable_preview=disable_preview,
        )
        return message_id, "text_fallback"


def send_welcome(
    token: str,
    chat_id: str,
    site_base: str,
    state: dict[str, Any],
    config: dict[str, Any],
) -> None:
    if state.get("welcome_message_id") or not config.get("welcome_enabled", True):
        return

    site_url = (
        site_base
        + "?"
        + urllib.parse.urlencode(
            {
                "utm_source": "telegram",
                "utm_medium": "social",
                "utm_campaign": "channel_reboot",
            }
        )
    )
    safe_url = html_lib.escape(site_url, quote=True)
    text = (
        "🚛 <b>СпецАвтоПортал — начинаем заново</b>\n\n"
        "Главное о рынке прицепов, полуприцепов и грузовой техники — без информационного шума.\n\n"
        "Здесь будут:\n"
        "• важные новости отрасли;\n"
        "• утренняя и вечерняя сводка;\n"
        "• новые модели и производители;\n"
        "• ГОСТы и регламенты простым языком;\n"
        "• практические гайды;\n"
        "• партнёрские материалы — только с явной пометкой.\n\n"
        f'🔗 <a href="{safe_url}">spec-avtoportal.ru</a>'
    )

    message_id = send_message(token, chat_id, text, site_url=site_url)
    state["welcome_message_id"] = message_id
    state["welcome_sent_at"] = utc_now()
    save_state(state)

    if config.get("pin_welcome", True):
        try:
            api_call(
                token,
                "pinChatMessage",
                {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "disable_notification": True,
                },
            )
        except Exception as exc:
            print(f"WARN: welcome post was sent but not pinned: {exc}", file=sys.stderr)


def main() -> int:
    config = load_config()
    if not config.get("enabled", False):
        print("Telegram publishing is paused.", file=sys.stderr)
        return 0

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not configured.", file=sys.stderr)
        return 0

    current = load_current()
    if not current:
        print("No news items found.", file=sys.stderr)
        return 0

    state = load_state()
    baseline = load_baseline(config, current)
    queue = get_unhandled_items(baseline, current, state)

    site_base = os.environ.get(
        "SITE_URL",
        "https://spec-avtoportal.ru/",
    ).rstrip("/") + "/"

    send_welcome(token, chat_id, site_base, state, config)

    max_age_hours = int(config.get("max_item_age_hours") or 48)
    configured_max = int(config.get("max_immediate_per_run") or 3)
    max_posts = int(os.environ.get("TELEGRAM_MAX_POSTS", str(configured_max)))
    disable_preview = os.environ.get("TELEGRAM_DISABLE_PREVIEW") == "1"

    fresh = [item for item in queue if is_recent(item, max_age_hours)]
    fresh.sort(key=item_date, reverse=True)
    immediate = fresh[:max_posts]

    if not immediate:
        print(
            f"No fresh Telegram items. queued={len(queue)}.",
            file=sys.stderr,
        )
        save_state(state)
        return 0

    key_to_index = {make_key(item): idx for idx, item in enumerate(current)}
    print(f"Publishing {len(immediate)} Telegram news item(s)...")
    errors = 0

    for item in immediate:
        key = make_key(item)
        idx = key_to_index.get(key)
        site_url = build_site_url(
            site_base,
            item,
            idx,
            medium="social",
            campaign="news",
        )
        text = build_text(item, site_url)

        try:
            message_id, visual_mode = send_visual_or_fallback(
                token,
                chat_id,
                item,
                text,
                site_url,
                disable_preview,
            )
            state["posts"][key] = {
                "message_id": message_id,
                "sent_at": utc_now(),
                "site_url": site_url,
                "title": str(item.get("title") or ""),
                "slug": str(item.get("slug") or ""),
                "kind": "news",
                "visual": visual_mode,
            }
            save_state(state)
            print(f" OK {message_id}: {str(item.get('title') or '')[:90]}")
        except Exception as exc:
            errors += 1
            print(f" ERR {str(item.get('title') or '')[:90]}: {exc}", file=sys.stderr)

    if errors:
        print(f"Telegram completed with {errors} error(s).", file=sys.stderr)
        return 1

    print("Telegram news publishing completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
