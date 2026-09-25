from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "ops_report",
    ROOT / "tools/build_ops_report.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class OpsReportContentTests(unittest.TestCase):
    def render(self, name: str, conclusion: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            event_path = Path(tmp) / "event.json"
            output_path = Path(tmp) / "report.txt"
            event_path.write_text(
                json.dumps(
                    {
                        "workflow_run": {
                            "name": name,
                            "conclusion": conclusion,
                            "html_url": "https://github.com/example/actions/runs/123",
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "GITHUB_EVENT_PATH": str(event_path),
                    "OPS_REPORT_PATH": str(output_path),
                },
                clear=False,
            ):
                MODULE.main()
            return output_path.read_text(encoding="utf-8")

    def test_successful_site_report_contains_information_not_github_link(self) -> None:
        report = self.render("Site — Build, Deploy & VK Publish", "success")

        self.assertIn("Актуальная версия сайта опубликована.", report)
        self.assertIn("В базе сайта сейчас", report)
        self.assertIn("От вас действий не требуется.", report)
        self.assertNotIn("github.com", report)
        self.assertNotIn("Подробности:", report)

    def test_failed_report_keeps_diagnostic_link(self) -> None:
        report = self.render("Checks — Full QA", "failure")

        self.assertIn("Задача завершилась с ошибкой.", report)
        self.assertIn("Технические подробности:", report)
        self.assertIn("github.com/example/actions/runs/123", report)


if __name__ == "__main__":
    unittest.main()
