from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .models import PromotionAction
from .tracking import build_tracking_url

SKIP_STATUSES = {
    "blocked",
    "disabled",
    "do_not_post",
    "do_not_contact",
    "paused",
    "paused_dns",
}


def target_priority(target: dict[str, Any]) -> int:
    explicit = target.get("priority")
    if isinstance(explicit, int):
        return explicit

    status = str(target.get("status") or "")
    if status == "priority_candidate":
        return 100
    if status in {"candidate", "approval_required"}:
        return 50
    return 10


def build_actions(
    campaign: dict[str, Any],
    targets_by_channel: dict[str, Iterable[dict[str, Any]]],
    completed: set[tuple[str, str]] | None = None,
) -> list[PromotionAction]:
    completed = completed or set()
    if campaign.get("status") != "active":
        return []

    campaign_id = str(campaign["id"])
    destination = str(campaign["destination"])
    utm_campaign = str(campaign.get("utm_campaign") or campaign_id)
    allowed = set(campaign.get("allowed_channels") or [])
    limits = campaign.get("limits") or {}
    actions: list[PromotionAction] = []

    for channel in allowed:
        raw_limit = limits.get(channel, 0)
        try:
            limit = max(0, int(raw_limit))
        except (TypeError, ValueError):
            limit = 0
        if limit == 0:
            continue

        candidates = []
        for target in targets_by_channel.get(channel, []):
            target_id = str(target.get("id") or "")
            if not target_id or (channel, target_id) in completed:
                continue
            if str(target.get("status") or "") in SKIP_STATUSES:
                continue
            candidates.append(target)

        candidates.sort(
            key=lambda item: (
                -target_priority(item),
                str(item.get("id") or ""),
            )
        )

        for target in candidates[:limit]:
            target_id = str(target["id"])
            action = str(target.get("planned_action") or "review")
            medium = str(target.get("utm_medium") or channel)
            content = str(target.get("utm_content") or action)
            tracking_url = build_tracking_url(
                destination,
                source=target_id,
                medium=medium,
                campaign=utm_campaign,
                content=content,
            )
            actions.append(
                PromotionAction(
                    campaign_id=campaign_id,
                    channel=channel,
                    target_id=target_id,
                    action=action,
                    destination=destination,
                    tracking_url=tracking_url,
                    priority=target_priority(target),
                    metadata={
                        "target_name": target.get("name"),
                        "automation": target.get("automation"),
                        "policy": target.get("policy"),
                    },
                )
            )

    actions.sort(key=lambda item: (-item.priority, item.channel, item.target_id))
    return actions
