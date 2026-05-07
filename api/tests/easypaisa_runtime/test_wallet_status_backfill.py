import unittest

from api.scripts.easypaisa_wallet_status_backfill import (
    collect_redis_candidate_ids,
    normalize_payment_id,
)


class FakeRedis:
    def __init__(self):
        self.hashes = {}
        self.zsets = {}
        self.sets = {}
        self.lists = {}

    def hkeys(self, key):
        return list(self.hashes.get(key, {}).keys())

    def zrange(self, key, start, stop):
        values = list(self.zsets.get(key, {}).keys())
        return values[start:] if stop == -1 else values[start : stop + 1]

    def smembers(self, key):
        return set(self.sets.get(key, set()))

    def lrange(self, key, start, stop):
        values = list(self.lists.get(key, []))
        return values[start:] if stop == -1 else values[start : stop + 1]

    def scan_iter(self, match=None, count=None):
        prefix = match[:-1] if match and match.endswith("*") else match
        for key in self.lists:
            if prefix is None or key.startswith(prefix):
                yield key


class WalletStatusBackfillTests(unittest.TestCase):
    def test_normalize_payment_id_accepts_bytes_and_digits_only(self):
        self.assertEqual(normalize_payment_id(b"533280"), 533280)
        self.assertEqual(normalize_payment_id(" 533281 "), 533281)
        self.assertIsNone(normalize_payment_id("533x"))
        self.assertIsNone(normalize_payment_id(""))

    def test_collect_redis_candidate_ids_uses_old_online_sources(self):
        redis = FakeRedis()
        redis.hashes["hash_easypaisa"] = {"533280": "{}"}
        redis.zsets["set_easypaisa"] = {"533281": 1}
        redis.sets["easypaisa_runtime:index:online"] = {"533282"}
        redis.sets["payment_online_df"] = {"533283"}
        redis.lists["payment_active_df"] = ["533284"]
        redis.lists["payment_active_1001"] = ["533285", "bad"]

        self.assertEqual(
            collect_redis_candidate_ids(redis),
            [533280, 533281, 533282, 533283, 533284, 533285],
        )


if __name__ == "__main__":
    unittest.main()
