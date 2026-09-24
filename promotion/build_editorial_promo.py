#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from promotion.core.manual_queue import upsert_manual_action
from promotion.core.tracking import build_tracking_url
KNOWLEDGE_PATH = ROOT / "frontend/data/knowledge_articles.json"
TARGETS_PATH = ROOT / "promotion/targets.json"
HISTORY_PATH = ROOT / "frontend/data/promotion/editorial_history.json"
LEGACY_HISTORY_PATH = ROOT / "frontend/data/promotion_history.json"
QUEUE_PATH = ROOT / "frontend/data/promotion/editorial_queue.json"
MANUAL_QUEUE_PATH = ROOT / "frontend/data/promotion/manual_queue.json"

MSK = timezone(timedelta(hours=3))
AUTO_TARGETS = {"mexzona"}
BLOCKED_TARGET_STATUSES = {"blocked", "do_not_post", "disabled"}
PUBLISHER_PLATFORMS = {"publisher"}
SUCCESS_STATUSES = {"submitted", "verified_in_author_cabinet", "published"}
COOLDOWN_DAYS = 7


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_dt(raw: str) -> datetime | None:
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    except Exception:
        return None


def last_target_action(history: list[dict[str, Any]], target_id: str) -> datetime | None:
    values = []
    for row in history:
        if str(row.get("target_id") or "") != target_id:
            continue
        dt = parse_dt(str(row.get("created_at") or row.get("submitted_at") or ""))
        if dt:
            values.append(dt)
    return max(values) if values else None


def in_cooldown(history: list[dict[str, Any]], target_id: str, now: datetime) -> bool:
    latest = last_target_action(history, target_id)
    return bool(latest and latest > now - timedelta(days=COOLDOWN_DAYS))


def words(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[а-яёa-z0-9]+", str(text or "").lower())
        if len(token) >= 5
    }


def relevance(article: dict[str, Any], target: dict[str, Any]) -> int:
    hay = " ".join(
        [
            str(article.get("title") or ""),
            str(article.get("eyebrow") or ""),
            str(article.get("description") or ""),
            str(article.get("lead") or ""),
        ]
    ).lower()
    return sum(1 for token in words(str(target.get("audience_hint") or "")) if token in hay)


def tracking_url(slug: str, target_id: str) -> str:
    return build_tracking_url(
        f"https://spec-avtoportal.ru/knowledge/{slug}/",
        source=target_id,
        medium="editorial",
        campaign="industry_editorial",
        content=slug,
    )


def article_body(article: dict[str, Any], site_url: str) -> str:
    lines = [
        str(article.get("title") or "Материал СпецАвтоПортала").strip(),
        "",
        str(article.get("lead") or article.get("description") or "").strip(),
    ]
    for section in article.get("sections") or []:
        if not isinstance(section, dict):
            continue
        heading = str(section.get("heading") or "").strip()
        if heading:
            lines += ["", heading]
        for paragraph in section.get("paragraphs") or []:
            text = str(paragraph).strip()
            if text:
                lines.append(text)
        for bullet in section.get("bullets") or []:
            text = str(bullet).strip()
            if text:
                lines.append("• " + text)
        for index, item in enumerate(section.get("numbered") or [], start=1):
            text = str(item).strip()
            if text:
                lines.append(f"{index}. {text}")
        for fact in section.get("facts") or []:
            if isinstance(fact, list) and len(fact) >= 2:
                lines.append(f"{fact[0]}: {fact[1]}")
    lines += ["", f"Источник и полная версия: {site_url}"]
    return "\n".join(x for x in lines if x is not None).strip()


def used_pairs(history: list[dict[str, Any]]) -> set[tuple[str, str]]:
    return {
        (str(row.get("target_id") or ""), str(row.get("slug") or ""))
        for row in history
        if row.get("status") in SUCCESS_STATUSES | {"manual_prepared"}
    }


def target_rank(target: dict[str, Any]) -> tuple[int, str]:
    target_id = str(target.get("id") or "")
    if target_id in AUTO_TARGETS:
        return (0, target_id)
    if target.get("status") == "priority_candidate":
        return (1, target_id)
    return (2, target_id)


def pick_action(
    articles: list[dict[str, Any]],
    targets: list[dict[str, Any]],
    history: list[dict[str, Any]],
    now: datetime,
) -> dict[str, Any] | None:
    done = used_pairs(history)
    candidates = [
        target
        for target in targets
        if target.get("platform") in PUBLISHER_PLATFORMS
        and target.get("status") not in BLOCKED_TARGET_STATUSES
        and target.get("policy") != "blocked"
        and not in_cooldown(history, str(target.get("id") or ""), now)
    ]
    candidates.sort(key=target_rank)

    for target in candidates:
        target_id = str(target.get("id") or "")
        ranked = sorted(
            articles,
            key=lambda item: (-relevance(item, target), str(item.get("slug") or "")),
        )
        for article in ranked:
            slug = str(article.get("slug") or "")
            if not slug or (target_id, slug) in done:
                continue
            site_url = tracking_url(slug, target_id)
            automatic = target_id in AUTO_TARGETS
            return {
                "target_id": target_id,
                "target_name": target.get("name"),
                "target_url": target.get("url"),
                "contact": target.get("contact"),
                "policy": target.get("policy"),
                "execution": "automatic" if automatic else "manual",
                "slug": slug,
                "item_key": "knowledge:" + slug,
                "title": article.get("title"),
                "site_url": site_url,
                "post_text": article_body(article, site_url),
                "status": "ready_for_publish" if automatic else "ready_for_manual",
            }
    return None


def manual_action(entry: dict[str, Any], now: str) -> dict[str, Any]:
    target_name = str(entry.get("target_name") or entry.get("target_id") or "Площадка")
    contact = str(entry.get("contact") or entry.get("target_url") or "").strip()
    return {
        "action_id": f"editorial:{entry.get('target_id')}:{entry.get('slug')}",
        "channel": "publisher",
        "target_id": entry.get("target_id"),
        "target_name": target_name,
        "action": "publish_editorial_material",
        "contact": contact,
        "status": "ready",
        "reason": "Для этой площадки пока нет подтверждённого автоматического входа или адаптера публикации.",
        "message": (
            f"Материал для размещения на «{target_name}»:"
            f"\n\n{entry.get('post_text') or ''}"
        ),
        "tracking_url": entry.get("site_url"),
        "created_at": now,
        "updated_at": now,
    }


def main() -> int:
    now = datetime.now(timezone.utc)
    now_text = utc_now()
    knowledge = load_json(KNOWLEDGE_PATH, {"items": []})
    targets_data = load_json(TARGETS_PATH, {"targets": []})
    history_data = load_json(HISTORY_PATH, {"entries": []})
    legacy_history_data = load_json(LEGACY_HISTORY_PATH, {"entries": []})
    manual_data = load_json(MANUAL_QUEUE_PATH, {"schema": 1, "entries": []})

    articles = [x for x in knowledge.get("items", []) if isinstance(x, dict)]
    targets = [x for x in targets_data.get("targets", []) if isinstance(x, dict)]
    editorial_history = [x for x in history_data.get("entries", []) if isinstance(x, dict)]
    legacy_history = [x for x in legacy_history_data.get("entries", []) if isinstance(x, dict)]
    planning_history = editorial_history + legacy_history
    action = pick_action(articles, targets, planning_history, now)

    entries = []
    if action:
        entries.append(action)
        if action["execution"] == "manual":
            upsert_manual_action(manual_data.setdefault("entries", []), manual_action(action, now_text))
            editorial_history.append(
                {
                    "target_id": action.get("target_id"),
                    "target_name": action.get("target_name"),
                    "slug": action.get("slug"),
                    "title": action.get("title"),
                    "site_url": action.get("site_url"),
                    "created_at": now_text,
                    "status": "manual_prepared",
                }
            )
            history_data["entries"] = editorial_history
            save_json(HISTORY_PATH, history_data)
            manual_data["updated_at"] = now_text
            save_json(MANUAL_QUEUE_PATH, manual_data)

    save_json(
        QUEUE_PATH,
        {
            "schema": 1,
            "generated_at": now_text,
            "campaign": "industry_editorial",
            "entries": entries,
        },
    )
    print(json.dumps({"planned": len(entries), "action": action}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
