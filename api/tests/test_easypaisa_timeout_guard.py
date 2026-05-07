import os
import sys
import unittest


CURRENT_DIR = os.path.dirname(__file__)
API_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
JOBS_ROOT = os.path.join(API_ROOT, "jobs")
for path in (API_ROOT, JOBS_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)


class FakeRedis:
    def __init__(self):
        self.sets = {}

    def sadd(self, key, value):
        self.sets.setdefault(key, set()).add(str(value))

    def sismember(self, key, value):
        return str(value) in self.sets.get(key, set())


class EasyPaisaTimeOutGuardTests(unittest.TestCase):
    def test_bank_type_field_also_routes_to_mysql_dispatch_state(self):
        from time_out import TimeOutGuard

        redis = FakeRedis()
        guard = TimeOutGuard(redis)

        self.assertFalse(guard.check(533280, bank_type_id=14, bank_type=97))
        redis.sadd(TimeOutGuard.INDEX_DISPATCH_DS, 533280)
        self.assertTrue(guard.check(533280, bank_type_id=14, bank_type=97))

    def test_non_easypaisa_still_allows_legacy_requeue(self):
        from time_out import TimeOutGuard

        guard = TimeOutGuard(FakeRedis())

        self.assertTrue(guard.check(888888, bank_type_id=14, bank_type=14))


if __name__ == "__main__":
    unittest.main()
