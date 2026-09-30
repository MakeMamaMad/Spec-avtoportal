import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import fetch_traffic_breakdown as ftb  # noqa: E402


class BreakdownTest(unittest.TestCase):
    def test_builds_all_cuts_and_keeps_going_on_errors(self):
        calls = []

        def fake(params, token):
            calls.append(params)
            if params["dimensions"] == "ym:s:lastSearchPhrase":
                raise ValueError("boom")
            return {"data": [{"dimensions": [{"name": "direct"}, {"name": None}], "metrics": [10, 8, 50.0, 1.5, 42]}], "totals": [10, 8, 50, 1.5, 42]}

        data = ftb.build("t", fake)
        week = data["last_7_days"]
        self.assertEqual(set(week), set(ftb.CUTS))
        self.assertEqual(week["sources"]["rows"][0], {"key": "direct / —", "visits": 10, "users": 8, "bounce": 50.0, "depth": 1.5, "duration_s": 42})
        self.assertIn("error", week["search_phrases"])
        direct_calls = [c for c in calls if c.get("filters") == ftb.DIRECT]
        self.assertTrue(direct_calls)
        self.assertIn("rows", data["daily_30"])


if __name__ == "__main__":
    unittest.main()
