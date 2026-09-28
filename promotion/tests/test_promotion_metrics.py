from __future__ import annotations

import unittest

from tools.promotion_metrics import format_feedback_lines, parse_rows


class PromotionMetricsTests(unittest.TestCase):
    def test_parse_rows_sorts_by_visits(self) -> None:
        payload = {
            "data": [
                {
                    "dimensions": [
                        {"name": "mexzona"},
                        {"name": "editorial"},
                        {"name": "industry_editorial"},
                    ],
                    "metrics": [3, 2, 10.5, 1.8, 75],
                },
                {
                    "dimensions": [
                        {"name": "com-stil-editorial"},
                        {"name": "editorial"},
                        {"name": "industry_editorial"},
                    ],
                    "metrics": [7, 5, 20, 2.4, 130],
                },
            ]
        }

        rows = parse_rows(payload)
        self.assertEqual(rows[0]["source"], "com-stil-editorial")
        self.assertEqual(rows[0]["visits"], 7)
        self.assertEqual(rows[0]["users"], 5)
        self.assertAlmostEqual(rows[0]["page_depth"], 2.4)

    def test_missing_token_is_explained(self) -> None:
        lines = format_feedback_lines(
            {"status": "not_configured", "days": 7, "rows": []}
        )
        self.assertIn("YANDEX_METRIKA_TOKEN", "\n".join(lines))

    def test_zero_utm_visits_are_explicit(self) -> None:
        lines = format_feedback_lines(
            {"status": "ok", "days": 7, "rows": []}
        )
        self.assertIn("0", "\n".join(lines))


if __name__ == "__main__":
    unittest.main()
