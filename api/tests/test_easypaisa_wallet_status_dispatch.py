import unittest


class FakeRedis:
    def __init__(self):
        self.sets = {"payment_online_ds": {"101", "533267", "bad"}}
        self.sismember_calls = []

    async def smembers(self, key):
        return self.sets.get(key, set())

    async def sismember(self, key, value):
        self.sismember_calls.append((key, str(value)))
        return str(value) in self.sets.get(key, set())


class ExplodingRedis(FakeRedis):
    async def smembers(self, key):
        raise AssertionError("代收可派单列表不应读取 Redis 在线集合")

    async def sismember(self, key, value):
        raise AssertionError("代收最终判断不应读取 Redis 在线集合")


class FakeHandler:
    def __init__(self, redis=None, payment_row=None):
        self.redis = redis or FakeRedis()
        self.payment_row = payment_row or {}
        self.query_sqls = []

    async def get_result_by_condition(self, table, fields, where):
        if table != "payment":
            return None
        return dict(self.payment_row)

    async def query(self, sql):
        self.query_sqls.append(sql)
        if "collection_status = 1" in sql:
            return [{"id": 533267}]
        if "id in" in sql:
            return [{"id": 101}]
        return []


class EasyPaisaWalletStatusDispatchTests(unittest.IsolatedAsyncioTestCase):
    def test_collection_dispatch_sql_uses_final_collection_status_only(self):
        from application.pay.pay import _collection_dispatch_extra_sql_condition

        sql = _collection_dispatch_extra_sql_condition("pay", "1010")

        self.assertIn("pay.collection_status = 1", sql)
        self.assertIn("find_in_set('1010'", sql)
        self.assertNotIn("pay.wallet_status = 1", sql)
        self.assertNotIn("pay.manual_status = 0", sql)
        self.assertNotIn("pay.status = 1", sql)
        self.assertNotIn("pay.certified = 1", sql)
        self.assertNotIn("bank_type_id = 97", sql)
        self.assertNotIn(" OR ", sql)

    def test_easypaisa_collection_formula_separates_wallet_and_business_state(self):
        from application.pay.pay import _is_collection_dispatch_enabled

        self.assertTrue(
            _is_collection_dispatch_enabled(
                {
                    "wallet_status": 1,
                    "account_accno": "98525348",
                    "collection_status": 1,
                    "status": 1,
                    "certified": 1,
                    "manual_status": 0,
                }
            )
        )
        self.assertFalse(
            _is_collection_dispatch_enabled(
                {
                    "wallet_status": 1,
                    "account_accno": "98525348",
                    "collection_status": 0,
                    "status": 0,
                    "certified": 0,
                    "manual_status": 1,
                }
            )
        )
        self.assertTrue(
            _is_collection_dispatch_enabled(
                {
                    "wallet_status": 1,
                    "account_accno": "98525348",
                    "collection_status": 1,
                    "status": 0,
                    "certified": 0,
                    "manual_status": 1,
                }
            )
        )
        self.assertFalse(
            _is_collection_dispatch_enabled(
                {
                    "wallet_status": 1,
                    "account_accno": "98525348",
                    "collection_status": 0,
                    "status": 1,
                    "certified": 1,
                    "manual_status": 0,
                }
            )
        )
        self.assertTrue(
            _is_collection_dispatch_enabled(
                {
                    "wallet_status": 0,
                    "account_accno": "",
                    "collection_status": 1,
                    "status": 0,
                    "certified": 0,
                    "manual_status": 1,
                }
            )
        )

    async def test_easypaisa_online_check_uses_mysql_row_not_redis(self):
        from application.pay.pay import _is_collection_payment_online

        handler = FakeHandler(redis=ExplodingRedis())

        online = await _is_collection_payment_online(
            handler,
            533267,
            97,
            bank_type=97,
            payment={
                "wallet_status": 1,
                "account_accno": "98525348",
                "collection_status": 1,
                "status": 1,
                "certified": 1,
                "manual_status": 0,
            },
        )

        self.assertTrue(online)

    async def test_collection_online_check_does_not_fallback_to_legacy_redis(self):
        from application.pay.pay import _is_collection_payment_online

        handler = FakeHandler(redis=FakeRedis())

        online = await _is_collection_payment_online(handler, 101, 98, bank_type=98)

        self.assertFalse(online)
        self.assertEqual(handler.redis.sismember_calls, [])

    async def test_collection_ids_use_mysql_only(self):
        from application.pay.pay import _collection_online_payment_ids

        handler = FakeHandler(redis=ExplodingRedis())

        payment_ids = await _collection_online_payment_ids(handler)

        self.assertEqual(payment_ids, ["533267"])
        self.assertTrue(any("collection_status = 1" in sql for sql in handler.query_sqls))
        self.assertFalse(any("wallet_status = 1" in sql for sql in handler.query_sqls))


if __name__ == "__main__":
    unittest.main()
