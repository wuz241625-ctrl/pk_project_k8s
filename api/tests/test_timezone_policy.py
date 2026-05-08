import importlib
import os
import sys
import unittest
import subprocess
from datetime import datetime, timezone
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


class TimezonePolicyTests(unittest.TestCase):
    def setUp(self):
        self.old_env = {
            "BUSINESS_TIMEZONE": os.environ.get("BUSINESS_TIMEZONE"),
            "APP_DISPLAY_TIMEZONE": os.environ.get("APP_DISPLAY_TIMEZONE"),
        }
        os.environ["BUSINESS_TIMEZONE"] = "UTC"
        os.environ["APP_DISPLAY_TIMEZONE"] = "Asia/Karachi"
        sys.modules.pop("application.timezone", None)

    def tearDown(self):
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        sys.modules.pop("application.timezone", None)

    def test_business_time_stays_utc_and_display_time_converts_to_pakistan(self):
        timezone_policy = importlib.import_module("application.timezone")

        self.assertEqual(timezone_policy.get_business_timezone_name(), "UTC")
        self.assertEqual(timezone_policy.get_display_timezone_name(), "Asia/Karachi")

        utc_value = datetime(2026, 5, 4, 17, 30, 0, tzinfo=timezone.utc)
        self.assertEqual(
            timezone_policy.format_for_display(utc_value),
            "2026-05-04 22:30:00",
        )

    def test_display_input_is_converted_back_to_naive_utc_for_queries(self):
        timezone_policy = importlib.import_module("application.timezone")

        self.assertEqual(
            timezone_policy.display_to_utc_naive("2026-05-04 22:30:00"),
            datetime(2026, 5, 4, 17, 30, 0),
        )

    def test_display_today_between_uses_pakistan_day_as_utc_query_range(self):
        timezone_policy = importlib.import_module("application.timezone")

        result = timezone_policy.display_today_between(
            "time_create",
            datetime(2026, 5, 4, 20, 30, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(result["key"], "time_create")
        self.assertEqual(result["start"], datetime(2026, 5, 4, 19, 0, 0))
        self.assertEqual(result["end"], datetime(2026, 5, 5, 18, 59, 59))

    def test_backend_code_has_no_shanghai_timezone_literal(self):
        result = subprocess.run(
            [
                "rg",
                "Asia" + "/Shanghai",
                "api",
                "admin",
                "merchant",
                "-g",
                "*.py",
            ],
            cwd=Path(__file__).resolve().parents[2],
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 1, result.stdout)


if __name__ == "__main__":
    unittest.main()
