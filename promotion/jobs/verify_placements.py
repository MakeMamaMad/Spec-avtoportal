#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from promotion.core.placements import (
    apply_verification_result,
    fetch_verification,
    is_due,
    sync_directory_placements,
    verification_url_for,
)
from promotion.core.state import load_json, save_json, utc_now

TARGETS_PATH = ROOT / "promotion/site_targets.json"
HISTORY_PATH = ROOT / "frontend/data/site_promo_history.json"
PLACEMENTS_PATH = ROOT / "frontend/data/promotion/placements.json"
SUMMARY_PATH = ROOT / "frontend/data/promotion/placement_verification_summary.json"


def main() -> int:
    targets_data = load_json(TARGETS_PATH, {"targets": []})
    history = load_json(HISTORY_PATH, {"entries": []})
    store = load_json(PLACEMENTS_PATH, {"schema": 1, "entries": []})

    targets = [x for x in targets_data.get("targets", []) if isinstance(x, dict)]
    history_rows = [x for x in history.get("entries", []) if isinstance(x, dict)]
    placements = [x for x in store.get("entries", []) if isinstance(x, dict)]
    targets_by_id = {
        str(target.get("id") or ""): target
        for target in targets
        if target.get("id")
    }

    created = sync_directory_placements(placements, history_rows, targets)
    now = datetime.now(timezone.utc)
    checked = 0
    changed = 0
    changes: list[dict[str, Any]] = []

    for placement in placements:
        if not is_due(placement, now):
            continue

        target_id = str(placement.get("target_id") or "")
        target = targets_by_id.get(target_id, {})
        url = verification_url_for(placement, target)

        before_state = str(placement.get("state") or "")
        if url:
            result = fetch_verification(url, target)
        else:
            result = {
                "outcome": "not_found",
                "url": None,
                "detail": "Публичный адрес размещения пока неизвестен.",
            }

        checked += 1
        if apply_verification_result(placement, result, now):
            changed += 1
        after_state = str(placement.get("state") or "")
        if before_state != after_state or result.get("outcome") in {"live", "rejected"}:
            changes.append(
                {
                    "target_id": target_id,
                    "target_name": placement.get("target_name"),
                    "before": before_state,
                    "after": after_state,
                    "live_url": placement.get("live_url"),
                    "detail": result.get("detail"),
                }
            )

    store = {
        "schema": 1,
        "updated_at": utc_now(),
        "entries": placements,
    }
    save_json(PLACEMENTS_PATH, store)

    counts = Counter(str(x.get("state") or "unknown") for x in placements)
    summary = {
        "schema": 1,
        "updated_at": utc_now(),
        "created": created,
        "checked": checked,
        "changed": changed,
        "states": dict(sorted(counts.items())),
        "changes": changes[-20:],
    }
    save_json(SUMMARY_PATH, summary)

    print(
        json.dumps(
            {
                "created": created,
                "checked": checked,
                "changed": changed,
                "states": dict(counts),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
