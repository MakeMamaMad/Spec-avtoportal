#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN_PATH = ROOT / "promotion/site_campaign.json"
TARGETS_PATH = ROOT / "promotion/site_targets.json"
QUEUE_PATH = ROOT / "frontend/data/site_promo_queue.json"
HISTORY_PATH = ROOT / "frontend/data/site_promo_history.json"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def main() -> int:
    campaign = load_json(CAMPAIGN_PATH, {})
    targets = load_json(TARGETS_PATH, {"targets": []})
    history = load_json(HISTORY_PATH, {"entries": []})

    completed = {
        row.get("target_id")
        for row in history.get("entries", [])
        if row.get("status") in {"submitted", "published", "accepted", "under_moderation"}
    }

    entries = []
    for target in targets.get("targets", []):
        if target.get("status") in {"blocked", "do_not_post"}:
            continue
        if target.get("id") in completed:
            continue

        entries.append({
            "target_id": target.get("id"),
            "target_name": target.get("name"),
            "platform": target.get("platform"),
            "submission_url": target.get("url"),
            "policy": target.get("policy"),
            "automation": target.get("automation"),
            "site_url": campaign.get("site_url"),
            "title": campaign.get("title"),
            "short_description": campaign.get("short_description"),
            "full_description": campaign.get("full_description"),
            "region": campaign.get("region"),
            "keywords": campaign.get("keywords", []),
            "preferred_categories": target.get("preferred_categories", campaign.get("categories", [])),
            "requires_email": target.get("requires_email"),
            "status": "ready",
        })

    output = {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "campaign": "spec-avtoportal-site",
        "entries": entries,
    }
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(entries)} site-promotion target(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
