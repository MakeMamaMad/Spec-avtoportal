"""Shared promotion primitives introduced by PR #81.

The core now also contains placement verification primitives. Existing
promotion executors remain compatible while later PRs migrate them gradually.
"""

from .models import PromotionAction, PromotionEvent, PromotionPlacement
from .tracking import build_tracking_url

__all__ = [
    "PromotionAction",
    "PromotionEvent",
    "PromotionPlacement",
    "build_tracking_url",
]
