#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "frontend/data/news.json"
TARGETS_PATH = ROOT / "promotion/targets.json"
QUEUE_PATH = ROOT / "frontend/data/promotion_queue.json"

MAX_ITEMS = int(os.getenv("PROMOTION_MAX_ITEMS", "3"))

def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default

def clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", str(text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text

def clamp(text: str, n: int) -> str:
    text = clean(text)
    if len(text) <= n:
        return text
    cut = text[: n - 1].rsplit(" ", 1)[0].rstrip(" ,.;:-")
    return (cut or text[: n - 1]).rstrip() + "…"

def item_key(item: dict[str, Any]) -> str:
    for key in ("canonical_url", "url", "link", "guid", "id", "slug"):
        if item.get(key):
            return str(item[key])
    return clean(item.get("title", ""))

def published_value(item: dict[str, Any]) -> str:
    for key in ("published_at", "published", "date", "created_at"):
        if item.get(key):
            return str(item[key])
    return ""

def build_site_url(item: dict[str, Any], target_id: str) -> str:
    base = "https://spec-avtoportal.ru/"
    slug = str(item.get("slug") or "").strip()
    params = urllib.parse.urlencode({
        "utm_source": target_id,
        "utm_medium": "referral",
        "utm_campaign": "external_promotion",
        "utm_content": slug or "news",
    })
    if slug:
        return f"{base}news/{urllib.parse.quote(slug)}/?{params}"
    return base + "?" + params

def relevance(item: dict[str, Any], target: dict[str, Any]) -> int:
    hay = " ".join([
        clean(item.get("title", "")),
        clean(item.get("summary", item.get("description", ""))),
        " ".join(str(x) for x in (item.get("tags") or [])),
    ]).lower()
    hints = re.findall(r"[а-яёa-z0-9]+", str(target.get("audience_hint", "")).lower())
    return sum(1 for word in hints if len(word) >= 5 and word in hay)

def make_post(item: dict[str, Any], target: dict[str, Any]) -> str:
    title = clamp(item.get("title", "Материал СпецАвтоПортала"), 150)
    summary = clamp(item.get("summary", item.get("description", "")), 420)
    url = build_site_url(item, target["id"])
    parts = [f"🚛 {title}"]
    if summary:
        parts += ["", summary]
    parts += ["", f"Подробнее: {url}"]
    return "\n".join(parts)

def make_pitch(item: dict[str, Any], target: dict[str, Any]) -> str:
    title = clamp(item.get("title", "материал"), 120)
    return (
        f"Здравствуйте! Ведём отраслевой СпецАвтоПортал по грузовой технике и прицепам. "
        f"Есть материал «{title}», который может быть полезен вашей аудитории. "
        f"Можно ли разместить его у вас со ссылкой на источник? "
        f"Если да, пришлю готовый короткий текст без навязчивой рекламы."
    )

def main() -> int:
    news = load_json(NEWS_PATH, [])
    cfg = load_json(TARGETS_PATH, {"targets": []})
    previous = load_json(QUEUE_PATH, {"entries": []})
    done_keys = {
        (e.get("target_id"), e.get("item_key"))
        for e in previous.get("entries", [])
        if e.get("status") in {"sent", "approved", "published"}
    }

    items = [x for x in news if isinstance(x, dict)]
    items.sort(key=published_value, reverse=True)
    items = items[:MAX_ITEMS]

    entries: list[dict[str, Any]] = []
    for target in cfg.get("targets", []):
        if target.get("status") == "do_not_post" or target.get("policy") == "blocked":
            continue
        ranked = sorted(items, key=lambda it: relevance(it, target), reverse=True)
        for item in ranked[:1]:
            key = item_key(item)
            if (target.get("id"), key) in done_keys:
                continue
            entries.append({
                "target_id": target.get("id"),
                "platform": target.get("platform"),
                "target_name": target.get("name"),
                "target_url": target.get("url"),
                "contact": target.get("contact"),
                "policy": target.get("policy"),
                "item_key": key,
                "title": clean(item.get("title", "")),
                "site_url": build_site_url(item, target.get("id", "external")),
                "post_text": make_post(item, target),
                "admin_pitch": make_pitch(item, target),
                "status": "ready_for_review",
            })

    out = {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "entries": entries,
    }
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(entries)} external-promotion drafts.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
