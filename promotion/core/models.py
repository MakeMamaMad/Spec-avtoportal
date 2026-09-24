from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class PromotionAction:
    campaign_id: str
    channel: str
    target_id: str
    action: str
    destination: str
    tracking_url: str
    status: str = "planned"
    priority: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PromotionEvent:
    event_id: str
    occurred_at: str
    campaign_id: str
    channel: str
    target_id: str
    action: str
    outcome: str
    placement_id: str | None = None
    tracking_url: str | None = None
    detail: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
