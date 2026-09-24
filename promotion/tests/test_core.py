from __future__ import annotations

import unittest

from promotion.core.planner import build_actions
from promotion.core.tracking import build_tracking_url


class TrackingTests(unittest.TestCase):
    def test_build_tracking_url_preserves_existing_query(self) -> None:
        url = build_tracking_url(
            "https://spec-avtoportal.ru/knowledge.html?topic=axle#limits",
            source="example",
            medium="editorial",
            campaign="portal_growth",
            content="article",
        )
        self.assertIn("topic=axle", url)
        self.assertIn("utm_source=example", url)
        self.assertIn("utm_medium=editorial", url)
        self.assertTrue(url.endswith("#limits"))


class PlannerTests(unittest.TestCase):
    def test_planner_respects_channel_limit_and_priority(self) -> None:
        campaign = {
            "id": "portal-growth",
            "status": "active",
            "destination": "https://spec-avtoportal.ru/",
            "utm_campaign": "portal_growth",
            "allowed_channels": ["directory"],
            "limits": {"directory": 1},
        }
        targets = {
            "directory": [
                {"id": "regular", "status": "candidate"},
                {"id": "priority", "status": "priority_candidate"},
            ]
        }

        actions = build_actions(campaign, targets)

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].target_id, "priority")
        self.assertEqual(actions[0].status, "planned")


if __name__ == "__main__":
    unittest.main()
