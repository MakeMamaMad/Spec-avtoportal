"""Shared promotion primitives introduced by PR #81.

This package is additive. Existing promotion workflows keep their current
runtime behaviour until later migration PRs explicitly adopt these modules.
"""

from .models import PromotionAction, PromotionEvent
from .tracking import build_tracking_url

__all__ = ["PromotionAction", "PromotionEvent", "build_tracking_url"]
