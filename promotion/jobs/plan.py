#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from promotion.core.planner import build_actions
from promotion.core.state import load_json, save_json, utc_now

CAMPAIGNS_PATH = ROOT / "promotion/config/campaigns.json"
SITE_TARGETS_PATH = ROOT / "promotion/site_targets.json"
TELEGRAM_TARGETS_PATH = ROOT / "promotion/telegram_targets.json"
PUBLISHER_TARGETS_PATH = ROOT / "promotion/targets.json"
OUTPUT_PATH = ROOT / "frontend/data/promotion/action_queue.json"


def normalize_site_targets(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for target in data.get("targets", []):
        if not isinstance(target, dict):
            continue
        row = dict(target)
        row.update(
            {
                "planned_action": "directory_submit",
                "utm_medium": "directory",
                "utm_content": "site_listing",
            }
        )
        rows.append(row)
    return rows


def normalize_telegram_targets(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for target in data.get("targets", []):
        if not isinstance(target, dict):
            continue
        row = dict(target)
        row.update(
            {
                "planned_action": "telegram_outreach",
                "utm_medium": "telegram",
                "utm_content": "community_promotion",
            }
        )
        rows.append(row)
    return rows


def normalize_publishers(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for target in data.get("targets", []):
        if not isinstance(target, dict):
            continue
        if target.get("platform") not in {"publisher", "press_release"}:
            continue
        row = dict(target)
        row.update(
            {
                "planned_action": "publisher_review",
                "utm_medium": "editorial",
                "utm_content": "article",
            }
        )
        rows.append(row)
    return rows


def main() -> int:
    campaigns = load_json(CAMPAIGNS_PATH, {"campaigns": []})
    targets_by_channel = {
        "directory": normalize_site_targets(
            load_json(SITE_TARGETS_PATH, {"targets": []})
        ),
        "telegram_community": normalize_telegram_targets(
            load_json(TELEGRAM_TARGETS_PATH, {"targets": []})
        ),
        "publisher": normalize_publishers(
            load_json(PUBLISHER_TARGETS_PATH, {"targets": []})
        ),
        "telegram_ads": [],
    }

    entries = []
    for campaign in campaigns.get("campaigns", []):
        if not isinstance(campaign, dict):
            continue
        entries.extend(
            action.to_dict()
            for action in build_actions(campaign, targets_by_channel)
        )

    save_json(
        OUTPUT_PATH,
        {
            "schema": 1,
            "generated_at": utc_now(),
            "mode": "planning_only",
            "entries": entries,
        },
    )
    print(f"Prepared {len(entries)} promotion action(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
