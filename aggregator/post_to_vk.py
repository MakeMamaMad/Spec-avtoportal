#!/usr/bin/env python3
"""VK Editorial publisher for SpecAvtoPortal.

Modes:
- immediate: publish recent new stories without importance scoring;
- digest: randomly select recent stories for a morning/evening digest.

Safety:
- archive items from before baseline_ref are never published;
- text fallback is used if visual upload fails;
- state prevents duplicate standalone posts and repeated digest items.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import random
import re
import subprocess
import sys
import urllib.parse
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


NEWS_PATH = Path("frontend/data/news.json")
STATE_PATH = Path("frontend/data/vk_state.json")
CONFIG_PATH = Path("aggregator/vk_config.json")

TAG_RE = re.compile(r"<[^>]+>")

CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Правила и контроль", ("гост", "тр тс", "закон", "регламент", "штраф", "тамож", "контроль")),
    ("Рынок и производство", ("рынок", "цена", "продаж", "производств", "завод", "выпуск")),
    ("Техника", ("полуприцеп", "прицеп", "тягач", "грузовик", "шасси", "ось", "тормоз", "подвеск")),
    ("Логистика", ("логист", "перевоз", "маршрут", "терминал", "склад", "порт", "контейнер")),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def strip_html(value: str) -> str:
    if not value:
        return ""
    text = TAG_RE.sub(" ", str(value))
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


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
    state["schema"] = 1
    state.setdefault("welcome_post_id", None)
    state.setdefault("welcome_sent_at", None)
    state.setdefault("posts", {})
    state.setdefault("digested", {})
    state.setdefault("digests", {})
    for key in ("posts", "digested", "digests"):
        if not isinstance(state[key], dict):
            state[key] = {}
    return state


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(STATE_PATH)


def load_current() -> list[dict[str, Any]]:
    data = load_json(NEWS_PATH, [])
    return data if isinstance(data, list) else []


def load_baseline(config: dict[str, Any], current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ref = str(config.get("baseline_ref") or "").strip()
    if not ref:
        print("WARN: VK baseline_ref is empty; publishing blocked.", file=sys.stderr)
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
        print(f"WARN: cannot load VK baseline {ref}: {exc}", file=sys.stderr)
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
    return "Отрасль"


def display_source(item: dict[str, Any]) -> str:
    source = str(item.get("source_name") or item.get("source") or "").strip()
    if source.lower() in {"", "source", "rss", "feed"}:
        source = str(item.get("domain") or "").replace("www.", "").strip()
    return source


def build_site_url(site_base: str, item: dict[str, Any], campaign: str) -> str:
    slug = str(item.get("slug") or "").strip()
    params = urllib.parse.urlencode(
        {
            "utm_source": "vk",
            "utm_medium": "social",
            "utm_campaign": campaign,
            "utm_content": slug or "news",
        }
    )
    if slug:
        return f"{site_base}news/{urllib.parse.quote(slug)}/?{params}"
    return f"{site_base}?{params}"


def original_url(item: dict[str, Any]) -> str:
    return str(
        item.get("canonical_url")
        or item.get("url")
        or item.get("link")
        or ""
    ).strip()


def unhandled_items(
    baseline: list[dict[str, Any]],
    current: list[dict[str, Any]],
    state: dict[str, Any],
) -> list[dict[str, Any]]:
    baseline_keys = {make_key(item) for item in baseline}
    posted = set(state["posts"])
    return [
        item
        for item in current
        if make_key(item) not in baseline_keys
        and make_key(item) not in posted
    ]


def news_message(item: dict[str, Any], site_url: str) -> str:
    title = strip_html(str(item.get("title") or "Новость отрасли"))
    summary = clamp(strip_html(str(item.get("summary") or item.get("description") or "")), 650)
    source = display_source(item)
    tags = [tag for tag in tags_for(item) if tag.lower() not in {"новости", "partner", "партнёр"}][:3]

    parts = ["📰 СпецАвтоПортал", "", title]
    if summary:
        parts.extend(["", summary])
    if tags:
        parts.extend(["", " · ".join(f"#{re.sub(r'[^0-9A-Za-zА-Яа-яЁё_]+', '', tag.replace(' ', '_'))}" for tag in tags)])
    if source:
        parts.extend(["", f"Источник: {source}"])
    parts.extend(["", f"Подробнее: {site_url}"])
    primary = original_url(item)
    if primary:
        parts.append(f"Первоисточник: {primary}")
    return "\n".join(parts)


def digest_message(items: list[dict[str, Any]], slot: str, site_base: str) -> str:
    label = "Утренняя" if slot == "am" else "Вечерняя"
    today = datetime.now(timezone.utc).strftime("%d.%m.%Y")
    lines = [
        f"🚛 {label} сводка СпецАвтоПортала · {today}",
        f"{len(items)} материалов к этому часу",
        "",
    ]
    for index, item in enumerate(items, 1):
        title = clamp(strip_html(str(item.get("title") or "Материал")), 150)
        url = build_site_url(site_base, item, f"{slot}_digest")
        lines.extend([f"{index}. {title}", url, ""])
    lines.append("spec-avtoportal.ru")
    return "\n".join(lines).strip()


def vk_api(method: str, token: str, api_version: str, **params: Any) -> Any:
    payload = {
        **params,
        "access_token": token,
        "v": api_version,
    }
    response = requests.post(
        f"https://api.vk.com/method/{method}",
        data=payload,
        timeout=30,
    )
    body = response.json()
    if "error" in body:
        error = body["error"]
        raise RuntimeError(
            f"VK {method}: {error.get('error_code')} {error.get('error_msg')}"
        )
    return body.get("response")


def group_id_from_response(response: Any) -> int:
    groups = response
    if isinstance(response, dict):
        groups = response.get("groups") or response.get("items") or []
    if isinstance(groups, list) and groups:
        group_id = groups[0].get("id") if isinstance(groups[0], dict) else None
        if isinstance(group_id, int):
            return abs(group_id)
    raise RuntimeError("VK groups.getById did not return numeric group id")


def resolve_group_id(
    token: str,
    api_version: str,
    screen_name: str,
    explicit_group_id: str = "",
) -> int:
    if explicit_group_id:
        try:
            return abs(int(explicit_group_id))
        except ValueError as exc:
            raise RuntimeError("VK_GROUP_ID must be numeric when provided") from exc

    if not screen_name:
        raise RuntimeError("VK community_screen_name is empty")

    response = vk_api(
        "groups.getById",
        token,
        api_version,
        group_ids=screen_name,
    )
    return group_id_from_response(response)


def guid_for(kind: str, key: str) -> str:
    return hashlib.sha256(f"specavto:{kind}:{key}".encode("utf-8")).hexdigest()[:32]


def wall_post(
    token: str,
    api_version: str,
    group_id: int,
    message: str,
    *,
    attachment: str = "",
    guid: str = "",
) -> int:
    params: dict[str, Any] = {
        "owner_id": -abs(group_id),
        "from_group": 1,
        "message": message,
    }
    if attachment:
        params["attachments"] = attachment
    if guid:
        params["guid"] = guid

    result = vk_api("wall.post", token, api_version, **params)
    post_id = (result or {}).get("post_id") if isinstance(result, dict) else None
    if not isinstance(post_id, int):
        raise RuntimeError("VK wall.post did not return post_id")
    return post_id


def wait_for_preview_page(url: str, attempts: int = 8, delay_seconds: int = 5) -> None:
    """Wait until the deployed article exposes its branded Open Graph image."""
    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(url, timeout=20, allow_redirects=True)
            body = response.text if response.ok else ""
            if response.ok and 'property="og:image"' in body and "/social/" in body:
                print(f"VK preview page ready on attempt {attempt}: {response.url}")
                return
            last_error = f"HTTP {response.status_code}; branded og:image not found"
        except Exception as exc:
            last_error = str(exc)
        if attempt < attempts:
            time.sleep(delay_seconds)
    raise RuntimeError(f"VK preview page is not ready: {last_error}")


def send_with_visual_fallback(
    token: str,
    api_version: str,
    group_id: int,
    message: str,
    *,
    kind: str,
    key: str,
    item: dict[str, Any] | None = None,
    slot: str = "",
) -> tuple[int, str]:
    """Publish a link post and let VK fetch the page Open Graph preview."""
    post_id = wall_post(
        token,
        api_version,
        group_id,
        message,
        guid=guid_for(kind, key),
    )
    return post_id, "link_preview"

def send_welcome(
    token: str,
    api_version: str,
    group_id: int,
    state: dict[str, Any],
    config: dict[str, Any],
    site_base: str,
) -> None:
    if state.get("welcome_post_id") or not config.get("welcome_enabled", True):
        return

    site_url = site_base + "?" + urllib.parse.urlencode(
        {
            "utm_source": "vk",
            "utm_medium": "social",
            "utm_campaign": "community_launch",
        }
    )
    message = (
        "🚛 СпецАвтоПортал теперь во ВКонтакте\n\n"
        "Главное о рынке прицепов, полуприцепов и грузовой техники — без информационного шума.\n\n"
        "Здесь будут важные новости, утренние и вечерние сводки, производители, "
        "регламенты и практические материалы.\n\n"
        f"Сайт: {site_url}"
    )
    post_id = wall_post(
        token,
        api_version,
        group_id,
        message,
        guid=guid_for("welcome", str(group_id)),
    )
    state["welcome_post_id"] = post_id
    state["welcome_sent_at"] = utc_now()
    save_state(state)


def digest_slot() -> str:
    forced = os.getenv("VK_DIGEST_SLOT", "").strip().lower()
    if forced in {"am", "pm"}:
        return forced
    return "am" if datetime.now(timezone.utc).hour < 12 else "pm"


def digest_id(slot: str) -> str:
    return f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}:{slot}"


def run_immediate(
    token: str,
    api_version: str,
    group_id: int,
    config: dict[str, Any],
    state: dict[str, Any],
    current: list[dict[str, Any]],
    baseline: list[dict[str, Any]],
    site_base: str,
) -> int:
    max_age = int(config.get("max_item_age_hours") or 48)
    max_posts = int(os.getenv("VK_MAX_POSTS", str(config.get("max_immediate_per_run") or 3)))

    candidates = [
        item
        for item in unhandled_items(baseline, current, state)
        if is_recent(item, max_age)
    ]
    candidates.sort(key=item_date, reverse=True)
    chosen = candidates[:max_posts]
    if not chosen:
        print("VK: no fresh unpublished news items.")
        return 0

    errors = 0
    for item in chosen:
        key = make_key(item)
        site_url = build_site_url(site_base, item, "news")
        message = news_message(item, site_url)
        try:
            wait_for_preview_page(site_url)
            post_id, visual = send_with_visual_fallback(
                token,
                api_version,
                group_id,
                message,
                kind="news",
                key=key,
                item=item,
            )
            state["posts"][key] = {
                "post_id": post_id,
                "sent_at": utc_now(),
                "title": str(item.get("title") or ""),
                "slug": str(item.get("slug") or ""),
                "site_url": site_url,
                "visual": visual,
            }
            save_state(state)
            print(f"VK OK post_id={post_id}: {str(item.get('title') or '')[:90]}")
        except Exception as exc:
            errors += 1
            print(f"VK ERR: {exc}", file=sys.stderr)

    return 1 if errors else 0


def run_digest(
    token: str,
    api_version: str,
    group_id: int,
    config: dict[str, Any],
    state: dict[str, Any],
    current: list[dict[str, Any]],
    baseline: list[dict[str, Any]],
    site_base: str,
) -> int:
    if not config.get("digest_enabled", True):
        print("VK digest disabled.")
        return 0

    slot = digest_slot()
    current_digest_id = digest_id(slot)
    if current_digest_id in state["digests"]:
        print(f"VK digest already sent: {current_digest_id}")
        return 0

    max_age = int(config.get("max_item_age_hours") or 48)
    limit = int(config.get("digest_items") or 5)
    min_items = int(config.get("digest_min_items") or 2)
    baseline_keys = {make_key(item) for item in baseline}
    already_digested = set(state["digested"])

    eligible = [
        item
        for item in current
        if make_key(item) not in baseline_keys
        and is_recent(item, max_age)
        and parse_item_datetime(item) is not None
    ]
    fresh = [item for item in eligible if make_key(item) not in already_digested]
    reused = [item for item in eligible if make_key(item) in already_digested]
    rng = random.SystemRandom()
    rng.shuffle(fresh)
    rng.shuffle(reused)
    items = (fresh + reused)[:limit]

    if len(items) < min_items:
        print(f"VK: not enough recent items for digest: {len(items)} < {min_items}")
        return 0

    message = digest_message(items, slot, site_base)
    post_id, visual = send_with_visual_fallback(
        token,
        api_version,
        group_id,
        message,
        kind="digest",
        key=current_digest_id,
        slot=slot,
    )

    sent_at = utc_now()
    state["digests"][current_digest_id] = {
        "post_id": post_id,
        "sent_at": sent_at,
        "slot": slot,
        "visual": visual,
        "items": [make_key(item) for item in items],
    }
    for item in items:
        state["digested"][make_key(item)] = {
            "digest_id": current_digest_id,
            "post_id": post_id,
            "sent_at": sent_at,
            "title": str(item.get("title") or ""),
            "slug": str(item.get("slug") or ""),
        }
    save_state(state)
    print(f"VK digest OK post_id={post_id} items={len(items)} slot={slot}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("immediate", "digest"), default="immediate")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        assert guid_for("news", "abc") == guid_for("news", "abc")
        assert group_id_from_response([{"id": 12345}]) == 12345
        assert group_id_from_response({"groups": [{"id": 67890}]}) == 67890
        print("VK Editorial self-test OK")
        return 0

    config = load_config()
    if not config.get("enabled", False):
        print("VK Editorial is prepared but paused.")
        return 0

    token = os.getenv("VK_ACCESS_TOKEN", "").strip()
    if not token:
        print("VK_ACCESS_TOKEN is not configured.", file=sys.stderr)
        return 0

    api_version = str(config.get("api_version") or "5.199")
    group_id = resolve_group_id(
        token,
        api_version,
        str(config.get("community_screen_name") or "").strip(),
        os.getenv("VK_GROUP_ID", "").strip(),
    )
    print(f"VK community resolved: id={group_id}")

    current = load_current()
    if not current:
        print("VK: no news items.")
        return 0

    state = load_state()
    baseline = load_baseline(config, current)
    site_base = os.getenv("SITE_URL", "https://spec-avtoportal.ru/").rstrip("/") + "/"

    if args.mode == "immediate":
        send_welcome(token, api_version, group_id, state, config, site_base)
        return run_immediate(
            token, api_version, group_id, config, state, current, baseline, site_base
        )
    return run_digest(
        token, api_version, group_id, config, state, current, baseline, site_base
    )


if __name__ == "__main__":
    raise SystemExit(main())
