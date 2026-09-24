from __future__ import annotations

import unittest
from datetime import datetime, timezone

from promotion.core.placements import (
    apply_verification_result,
    body_has_listing,
    probable_public_result,
    sync_directory_placements,
)


class PlacementSyncTests(unittest.TestCase):
    def test_submission_creates_pending_placement(self) -> None:
        placements = []
        history = [
            {
                "target_id": "example",
                "target_name": "Example",
                "attempted_at": "2026-09-24T10:00:00+00:00",
                "status": "under_moderation",
                "result_url": "https://example.test/add",
                "tracking_url": "https://spec-avtoportal.ru/?utm_source=example",
            }
        ]
        targets = [{"id": "example", "name": "Example", "url": "https://example.test/add"}]

        created = sync_directory_placements(placements, history, targets)

        self.assertEqual(created, 1)
        self.assertEqual(placements[0]["state"], "pending_review")
        self.assertEqual(placements[0]["next_check_at"], "2026-09-25T10:00:00+00:00")

    def test_published_history_marks_live(self) -> None:
        placements = []
        history = [
            {
                "target_id": "example",
                "published_at": "2026-09-24T10:00:00+00:00",
                "status": "published",
                "result_url": "https://example.test/sites/specavto",
            }
        ]
        targets = [{"id": "example", "url": "https://example.test/add"}]

        sync_directory_placements(placements, history, targets)

        self.assertEqual(placements[0]["state"], "live")
        self.assertEqual(placements[0]["live_url"], "https://example.test/sites/specavto")


class VerificationTests(unittest.TestCase):
    def test_form_url_is_not_public_result(self) -> None:
        self.assertFalse(
            probable_public_result(
                "https://example.test/addsite?done=1",
                "https://example.test/addsite",
            )
        )

    def test_listing_evidence_is_strict(self) -> None:
        self.assertTrue(body_has_listing("<a>https://spec-avtoportal.ru/</a>", {}))
        self.assertTrue(body_has_listing("<h1>СпецАвтоПортал</h1>", {}))
        self.assertFalse(body_has_listing("<h1>Другой сайт</h1>", {}))

    def test_two_missing_checks_remove_previously_live_placement(self) -> None:
        placement = {
            "state": "live",
            "submitted_at": "2026-09-20T10:00:00+00:00",
            "check_days": [1, 3, 7, 14, 30],
            "check_index": 0,
            "checks": [],
            "missing_count": 0,
            "live_url": "https://example.test/site/specavto",
        }

        apply_verification_result(
            placement,
            {"outcome": "missing", "url": placement["live_url"], "detail": "HTTP 404"},
            datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(placement["state"], "live")

        apply_verification_result(
            placement,
            {"outcome": "missing", "url": placement["live_url"], "detail": "HTTP 404"},
            datetime(2026, 9, 23, 10, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(placement["state"], "removed")
        self.assertIsNone(placement["next_check_at"])


if __name__ == "__main__":
    unittest.main()
