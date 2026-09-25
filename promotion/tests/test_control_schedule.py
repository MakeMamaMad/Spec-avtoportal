from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "control_schedule",
    ROOT / "tools/publish_control_schedule.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ControlScheduleTests(unittest.TestCase):
    def test_schedule_contains_current_main_times(self) -> None:
        text = MODULE.build_schedule_text()

        for value in (
            "09:30",
            "09:40",
            "10:15",
            "10:30",
            "11:45",
            "12:30",
            "13:15",
            "14:00",
            "18:30",
            "19:30",
            "19:40",
            "20:45",
        ):
            self.assertIn(value, text)

        self.assertIn("Каждые 3 часа", text)
        self.assertIn("YouTube Shorts, TikTok и Instagram Reels", text)
        self.assertIn("Кому написать сегодня", text)
        self.assertIn("Все времена — по Москве", text)


if __name__ == "__main__":
    unittest.main()
