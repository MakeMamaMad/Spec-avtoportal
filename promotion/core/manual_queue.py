from __future__ import annotations

from typing import Any

FINAL_STATUSES = {"completed", "dismissed"}


def upsert_manual_action(
    entries: list[dict[str, Any]],
    action: dict[str, Any],
) -> str:
    action_id = str(action.get("action_id") or "").strip()
    if not action_id:
        raise ValueError("manual action requires action_id")

    for existing in entries:
        if str(existing.get("action_id") or "") != action_id:
            continue

        if str(existing.get("status") or "") in FINAL_STATUSES:
            return "unchanged"

        created_at = existing.get("created_at") or action.get("created_at")
        changed = False
        for key, value in action.items():
            if key == "created_at":
                continue
            if existing.get(key) != value:
                existing[key] = value
                changed = True
        if created_at:
            existing["created_at"] = created_at
        return "updated" if changed else "unchanged"

    entries.append(dict(action))
    return "created"
