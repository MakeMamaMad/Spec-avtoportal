import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import rto_calculator as rto  # noqa: E402

NODE = shutil.which("node")


def plan(**opts):
    script = rto.PLANNER_JS + "\nconsole.log(JSON.stringify(planTrip(%s, %s)));" % (
        json.dumps({"startMs": 0, "extDays": 0, "reducedRest": False, **opts}),
        json.dumps(rto.LIMITS),
    )
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


@unittest.skipUnless(NODE, "node is not installed")
class PlannerTest(unittest.TestCase):
    def test_short_trip_single_block(self):
        p = plan(driveMin=240)
        self.assertEqual(p["days"], 1)
        self.assertEqual(p["totalMin"], 240)

    def test_break_after_four_and_a_half_hours(self):
        p = plan(driveMin=540)
        day = p["events"][0]
        self.assertEqual([s["min"] for s in day["segments"]], [270, 45, 270])
        self.assertEqual(p["totalMin"], 585)

    def test_twenty_hours_standard(self):
        # 9h (+45) / rest 11h / 9h (+45) / rest 11h / 2h
        p = plan(driveMin=1200)
        self.assertEqual(p["days"], 3)
        self.assertEqual(p["totalMin"], 585 + 660 + 585 + 660 + 120)
        self.assertEqual(p["extDays"], 0)

    def test_extended_days_and_reduced_rest(self):
        p = plan(driveMin=1200, extDays=2, reducedRest=True)
        # 10h (270+45+270+45+60) / rest 9h / 10h
        self.assertEqual(p["days"], 2)
        self.assertEqual(p["extDays"], 2)
        self.assertEqual(p["reducedRests"], 1)
        self.assertEqual(p["totalMin"], 690 + 540 + 690)

    def test_weekly_limit_forces_weekly_rest(self):
        # 60h of driving is more than 56h per week
        p = plan(driveMin=3600)
        self.assertGreaterEqual(p["weeklyRests"], 1)
        week_drive = 0
        for e in p["events"]:
            if e["type"] == "weekly":
                break
            if e["type"] == "day":
                week_drive += e["drive"]
                self.assertLessEqual(e["drive"], 540)
        self.assertLessEqual(week_drive, 3360)

    def test_no_day_exceeds_limits(self):
        p = plan(driveMin=5000, extDays=2, reducedRest=True)
        for e in p["events"]:
            if e["type"] == "day":
                self.assertLessEqual(e["drive"], 600)
                for s in e["segments"]:
                    if s["kind"] == "drive":
                        self.assertLessEqual(s["min"], 270)


class PageTest(unittest.TestCase):
    def test_page_renders_key_norms(self):
        page = rto.render_rto_calculator_page("https://spec-avtoportal.ru", "")
        for marker in ("приказ", "45 минут", "11 часов", "56 часов", 'rel="canonical"', "FAQPage", "planTrip"):
            self.assertIn(marker, page)


if __name__ == "__main__":
    unittest.main()
