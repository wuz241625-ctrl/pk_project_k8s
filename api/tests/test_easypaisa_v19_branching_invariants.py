import re
import unittest
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
SRC = API_ROOT / "application" / "app" / "login" / "banks" / "easypaisa.py"


class BranchingInvariantTests(unittest.TestCase):
    def setUp(self):
        self.src = SRC.read_text(encoding="utf-8")

    def test_dead_second_login_chain_symbol_absent(self):
        self.assertNotIn("_second_login_chain_from_pre_login", self.src)

    def test_pre_login_http_does_not_call_is_account_registered(self):
        match = re.search(r"async def pre_login_http\(self, data\):.*?\n    async def ", self.src, re.S)
        self.assertIsNotNone(match, "pre_login_http body not found")
        self.assertNotIn("_is_account_registered", match.group(0))


if __name__ == "__main__":
    unittest.main()
