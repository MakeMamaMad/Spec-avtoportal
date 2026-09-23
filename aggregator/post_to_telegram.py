#!/usr/bin/env python3
"""Publish new SpecAvtoPortal items to Telegram.

Telegram reboot model:
- a fixed baseline commit marks everything that existed before the channel reset;
- only items added after that baseline are eligible for publishing;
- successful Telegram message_ids are persisted so retries do not duplicate posts;
- failed items remain unposted and are retried on the next run;
- a one-time welcome post is sent after Telegram publishing is enabled.
"""
from __future__ import annotations

import html as html_lib
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(STATE_PATH)


def load_config() -> dict[str, Any]:
    config = load_json(CONFIG_PATH, {})
    return config if isinstance(config, dict) else {}


def load_state() -> dict[str, Any]:
    state = load_json(
        STATE_PATH,
        {
            "schema": 1,
            "welcome_message_id": None,
            "welcome_sent_at": None,
            "posts": {},
        },
    )
    if not isinstance(state, dict):
        state = {}
    state.setdefault("schema", 1)
    state.setdefault("welcome_message_id", None)
    state.setdefault("welcome_sent_at", None)
    state.setdefault("posts", {})
    if not isinstance(state["posts"], dict):
        state["posts"] = {}
    return state


def load_current() -> list[dict[str, Any]]:
    data = load_json(NEWS_PATH, [])
    return data if isinstance(data, list) else []


def load_baseline(config: dict[str, Any], current: list[dict[str, Any]]) -> list[dict[str, Any]]:
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


def get_publish_queue(
    baseline: list[dict[str, Any]],
    current: list[dict[str, Any]],
    state: dict[str, Any],
) -> list[dict[str, Any]]:
    baseline_keys = {make_key(item) for item in baseline}
    posted_keys = set(state.get("posts", {}).keys())

    queue = [
        item
        for item in current
        if make_key(item) not in baseline_keys and make_key(item) not in posted_keys
    ]
    queue.sort(key=item_date)
    return queue


def build_site_url(site_base: str, item: dict[str, Any], idx: int | None = None) -> str:
    slug = str(item.get("slug") or "").strip()
    if slug:
        path = f"news/{urllib.parse.quote(slug)}/"
        query = urllib.parse.urlencode(
            {
                "utm_source": "telegram",
                "utm_medium": "social",
                "utm_campaign": "news",
                "utm_content": slug,
            }
        )
        return f"{site_base}{path}?{query}"

    if isinstance(idx, int):
        query = urllib.parse.urlencode(
            {
                "i": idx,
                "utm_source": "telegram",
                "utm_medium": "social",
                "utm_campaign": "news",
            }
        )
        return f"{site_base}article.html?{query}"
    return ""


def display_source(item: dict[str, Any]) -> str:
    source = str(item.get("source_name") or item.get("source") or "").strip()
    if source.lower() in {"", "source", "rss", "feed"}:
        source = str(item.get("domain") or "").replace("www.", "").strip()
    return source


def build_text(item: dict[str, Any], site_url: str) -> str:
    title = html_lib.escape(str(item.get("title") or "(без заголовка)").strip())
    source = html_lib.escape(display_source(item))

    raw_summary = item.get("summary") or item.get("description") or ""
    summary = html_lib.escape(clamp(strip_html(str(raw_summary)), 430))

    tags = item.get("tags") or item.get("rubrics") or []
    if isinstance(tags, str):
        tags = [tags]
    if not isinstance(tags, list):
        tags = []
    tags = [
        html_lib.escape(str(tag).strip())
        for tag in tags
        if str(tag).strip() and str(tag).strip().lower() not in {"новости", "partner", "партнёр"}
    ][:3]

    original_url = str(
        item.get("canonical_url")
        or item.get("url")
        or item.get("link")
        or ""
    ).strip()

    parts = [f"🚛 <b>{title}</b>"]
    if summary:
        parts.append(summary)

    if tags:
        parts.append("🏷 " + " · ".join(tags))
    if source:
        parts.append(f"🌐 {source}")

    if site_url:
        safe_site = html_lib.escape(site_url, quote=True)
        parts.append("")
        parts.append(f'🔗 <a href="{safe_site}">Читать на СпецАвтоПортале</a>')

    if original_url:
        safe_original = html_lib.escape(original_url, quote=True)
        parts.append(f'<a href="{safe_original}">Первоисточник ↗</a>')

    return clamp("\n".join(parts), 3900)


def api_call(token: str, method: str, payload: dict[str, Any]) -> dict[str, Any]:
    api_url = f"https://api.telegram.org/bot{token}/{method}"
    encoded = {}
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


def send_welcome(
    token: str,
    chat_id: str,
    site_base: str,
    state: dict[str, Any],
    config: dict[str, Any],
) -> None:
    if state.get("welcome_message_id"):
        return
    if not config.get("welcome_enabled", True):
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
        "• новые модели и производители;\n"
        "• ГОСТы и регламенты простым языком;\n"
        "• практические гайды;\n"
        "• партнёрские материалы — только с явной пометкой.\n\n"
        f'🔗 <a href="{safe_url}">spec-avtoportal.ru</a>'
    )

    message_id = send_message(
        token,
        chat_id,
        text,
        site_url=site_url,
        disable_preview=False,
    )
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
        print("Telegram publishing is paused for the channel reboot.", file=sys.stderr)
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
    queue = get_publish_queue(baseline, current, state)

    site_base = os.environ.get(
        "SITE_URL",
        "https://spec-avtoportal.ru/",
    ).rstrip("/") + "/"

    send_welcome(token, chat_id, site_base, state, config)

    configured_max = int(config.get("max_posts_per_run") or 8)
    max_posts = int(os.environ.get("TELEGRAM_MAX_POSTS", str(configured_max)))
    disable_preview = os.environ.get("TELEGRAM_DISABLE_PREVIEW") == "1"

    if not queue:
        print("No unpublished Telegram news after reboot baseline.", file=sys.stderr)
        return 0

    queue = queue[-max_posts:]
    key_to_index = {make_key(item): idx for idx, item in enumerate(current)}

    print(f"Publishing {len(queue)} Telegram item(s)...")
    errors = 0

    for item in queue:
        key = make_key(item)
        title_dbg = str(item.get("title") or "")[:90]
        idx = key_to_index.get(key)
        site_url = build_site_url(site_base, item, idx)
        text = build_text(item, site_url)

        try:
            message_id = send_message(
                token,
                chat_id,
                text,
                site_url=site_url,
                disable_preview=disable_preview,
            )
            state["posts"][key] = {
                "message_id": message_id,
                "sent_at": utc_now(),
                "site_url": site_url,
                "title": str(item.get("title") or ""),
                "slug": str(item.get("slug") or ""),
            }
            save_state(state)
            print(f" OK {message_id}: {title_dbg}")
        except Exception as exc:
            errors += 1
            print(f" ERR {title_dbg}: {exc}", file=sys.stderr)

    if errors:
        print(f"Telegram completed with {errors} error(s).", file=sys.stderr)
        return 1

    print("Telegram publishing completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
