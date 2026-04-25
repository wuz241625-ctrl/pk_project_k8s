import asyncio
import os
import sys
import unittest


CURRENT_DIR = os.path.dirname(__file__)
ADMIN_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if ADMIN_ROOT not in sys.path:
    sys.path.insert(0, ADMIN_ROOT)

from application.base import BaseHandler


class FakeRedis:
    def __init__(self):
        self.values = {"cache_info_sys_info_1": "{}"}
        self.set_calls = []

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value):
        self.values[key] = value
        self.set_calls.append((key, value))


class FakeLogger:
    def info(self, *args, **kwargs):
        pass


class CacheResultTests(unittest.TestCase):
    def test_refreshes_cache_when_requested_key_is_missing(self):
        handler = object.__new__(BaseHandler)
        handler.redis = FakeRedis()
        handler.logger = FakeLogger()

        async def get_result_by_condition(table, keys, condition):
            return {"id": 1, "sys_ip_w": "103.135.100.192"}

        handler.get_result_by_condition = get_result_by_condition

        result = asyncio.run(handler.get_cache_result("sys_info", ["sys_ip_w"], {"id": 1}))

        self.assertEqual(result, {"sys_ip_w": "103.135.100.192"})
        self.assertTrue(handler.redis.set_calls)


if __name__ == "__main__":
    unittest.main()
