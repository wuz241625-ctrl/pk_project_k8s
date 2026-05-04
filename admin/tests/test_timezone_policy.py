import importlib
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


ADMIN_ROOT = Path(__file__).resolve().parents[1]
if str(ADMIN_ROOT) not in sys.path:
    sys.path.insert(0, str(ADMIN_ROOT))


class AdminTimezonePolicyTests(unittest.TestCase):
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

    def test_display_format_uses_pakistan_timezone_while_storage_stays_utc(self):
        timezone_policy = importlib.import_module("application.timezone")

        utc_value = datetime(2026, 5, 4, 17, 30, 0, tzinfo=timezone.utc)
        self.assertEqual(timezone_policy.get_business_timezone_name(), "UTC")
        self.assertEqual(
            timezone_policy.format_for_display(utc_value),
            "2026-05-04 22:30:00",
        )


if __name__ == "__main__":
    unittest.main()
