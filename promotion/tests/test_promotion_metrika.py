from __future__ import annotations

import unittest

from tools.fetch_promotion_metrika import normalize


class PromotionMetrikaTests(unittest.TestCase):
    def test_normalize_keeps_only_promotion_campaigns(self) -> None:
        payload = {
            "data": [
                {
                    "dimensions": [
                        {"name": "com-stil-editorial"},
                        {"name": "editorial"},
                        {"name": "industry_editorial"},
                    ],
                    "metrics": [7, 5, 14.2857, 2.4, 91.2],
                },
                {
                    "dimensions": [
                        {"name": "google"},
                        {"name": "organic"},
                        {"name": ""},
                    ],
                    "metrics": [100, 80, 20, 1.5, 45],
                },
            ]
        }
        rows = normalize(payload)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "com-stil-editorial")
        self.assertEqual(rows[0]["visits"], 7)
        self.assertEqual(rows[0]["users"], 5)
        self.assertEqual(rows[0]["campaign"], "industry_editorial")

    def test_normalize_sorts_by_visits(self) -> None:
        payload = {
            "data": [
                {
                    "dimensions": [
                        {"name": "a"},
                        {"name": "telegram"},
                        {"name": "community_promotion"},
                    ],
                    "metrics": [2, 2, 0, 1, 10],
                },
                {
                    "dimensions": [
                        {"name": "b"},
                        {"name": "directory"},
                        {"name": "catalog_promotion"},
                    ],
                    "metrics": [5, 4, 0, 1, 10],
                },
            ]
        }
        rows = normalize(payload)
        self.assertEqual([row["source"] for row in rows], ["b", "a"])


if __name__ == "__main__":
    unittest.main()
