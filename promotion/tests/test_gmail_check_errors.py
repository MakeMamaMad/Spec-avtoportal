import importlib.util
import json
import sys
import types
import unittest
import urllib.error
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]

# check_gmail_bounces imports google-auth at module level; stub it when absent.
for name in ("google", "google.auth", "google.auth.transport", "google.auth.transport.requests", "google.oauth2", "google.oauth2.credentials"):
    sys.modules.setdefault(name, types.ModuleType(name))
sys.modules["google.auth.transport.requests"].Request = getattr(sys.modules["google.auth.transport.requests"], "Request", object)
sys.modules["google.oauth2.credentials"].Credentials = getattr(sys.modules["google.oauth2.credentials"], "Credentials", object)

spec = importlib.util.spec_from_file_location("check_gmail_bounces", ROOT / "promotion/check_gmail_bounces.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)

sys.path.insert(0, str(ROOT / "tools"))
import send_filtered_control_notification as notify  # noqa: E402


class ClassifyTest(unittest.TestCase):
    def test_invalid_grant(self):
        err = check.classify_error(RuntimeError("('invalid_grant: Token has been expired or revoked.', {})"))
        self.assertEqual(err["code"], "token_expired_or_revoked")
        self.assertIn("GMAIL_TOKEN_B64", err["hint"])

    def test_http_503_is_temporary(self):
        exc = urllib.error.HTTPError("https://gmail", 503, "unavailable", {}, None)
        self.assertEqual(check.classify_error(exc)["code"], "gmail_http_503")

    def test_secret_values_are_masked(self):
        err = check.classify_error(RuntimeError("bad ya29.a0AfH6SMsecret and 1//0gRefresh"))
        self.assertNotIn("a0AfH6SMsecret", err["detail"])
        self.assertNotIn("0gRefresh", err["detail"])


class MainTest(unittest.TestCase):
    def test_failure_is_recorded_with_streak(self):
        with TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            with mock.patch.object(check, "STATE_PATH", state), mock.patch.object(
                check, "run", side_effect=RuntimeError("invalid_grant")
            ):
                self.assertEqual(check.main(), 1)
                self.assertEqual(check.main(), 1)
            saved = json.loads(state.read_text())
            self.assertEqual(saved["last_error"]["streak"], 2)


class NotificationTest(unittest.TestCase):
    def message(self, streak):
        payload = {"code": "token_expired_or_revoked", "hint": "Токен Gmail истёк", "streak": streak}
        log = "GMAIL_BOUNCE_CHECK_ERROR " + json.dumps(payload, ensure_ascii=False) + "\n"
        with mock.patch.object(notify, "source_log", return_value=log):
            return notify.build_bounce_message("failure")

    def test_first_failure_explains_reason(self):
        text = self.message(1)
        self.assertIn("Токен Gmail истёк", text)
        self.assertIn("token_expired_or_revoked", text)

    def test_repeated_failures_are_not_spammed(self):
        self.assertIsNone(self.message(2))
        self.assertIsNotNone(self.message(24))


if __name__ == "__main__":
    unittest.main()
