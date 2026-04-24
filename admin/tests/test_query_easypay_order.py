"""单元测试: query_easypay_order (easypay 三方补单).

覆盖 AC-2..AC-10 + 手机号归一化 + XML 解析.
参考 admin/tests/test_otherpay_option_label.py 的 sys.path 风格.
"""
import asyncio
import os
import sys
import unittest
from unittest.mock import MagicMock, patch


CURRENT_DIR = os.path.dirname(__file__)
ADMIN_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if ADMIN_ROOT not in sys.path:
    sys.path.insert(0, ADMIN_ROOT)

from application.order.query_third_order_status import (  # noqa: E402
    _easypay_build_inquire_xml,
    _easypay_norm_msisdn,
    _easypay_parse_inquire,
    query_easypay_order,
)


# ---------------------------------------------------------------------------
# Fixtures: 生产真实响应变体 (2026-04-17 抓取)
# ---------------------------------------------------------------------------
FIX_PAID = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
    '<soapenv:Body><ns3:inquireTransactionResponseType'
    ' xmlns:ns2="http://dto.common.pg.systems.com/"'
    ' xmlns:ns3="http://dto.transaction.partner.pg.systems.com/">'
    '<ns2:responseCode>0000</ns2:responseCode>'
    '<orderId>S17762732848219673450</orderId>'
    '<storeId>1257141</storeId>'
    '<storeName>SmM TRADER</storeName>'
    '<transactionId>149222628</transactionId>'
    '<transactionStatus>PAID</transactionStatus>'
    '<transactionAmount>300.0</transactionAmount>'
    '<transactionDateTime>2026-04-15T22:15:03.000+05:00</transactionDateTime>'
    '<msisdn>03145567308</msisdn>'
    '<paymentMode>MA</paymentMode>'
    '</ns3:inquireTransactionResponseType></soapenv:Body></soapenv:Envelope>'
)

FIX_FAILED = FIX_PAID.replace('>PAID<', '>FAILED<')
FIX_MSISDN_MISMATCH = FIX_PAID.replace('>03145567308<', '>03999999999<')
FIX_AMOUNT_MISMATCH = FIX_PAID.replace('>300.0<', '>500.0<')

# responseCode=0003（订单不存在），缺 msisdn / transactionStatus / transactionAmount
FIX_NOT_FOUND = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
    '<soapenv:Body><ns3:inquireTransactionResponseType'
    ' xmlns:ns2="http://dto.common.pg.systems.com/"'
    ' xmlns:ns3="http://dto.transaction.partner.pg.systems.com/">'
    '<ns2:responseCode>0003</ns2:responseCode>'
    '<storeId>0</storeId>'
    '<transactionAmount>0.0</transactionAmount>'
    '</ns3:inquireTransactionResponseType></soapenv:Body></soapenv:Envelope>'
)

# 响应缺 msisdn（但其他字段俱在）
FIX_NO_MSISDN = FIX_PAID.replace('<msisdn>03145567308</msisdn>', '')

# 响应缺 transactionAmount
FIX_NO_AMOUNT = FIX_PAID.replace('<transactionAmount>300.0</transactionAmount>', '')


# ---------------------------------------------------------------------------
# 构造假的 self（BaseHandler 实例）
# ---------------------------------------------------------------------------
def build_fake_self(admin_utr='03145567308',
                    otherpay_rows=None,
                    orders_rows=None):
    if otherpay_rows is None:
        otherpay_rows = [{'pay_url': 'https://fake-easypay/soap'}]
    if orders_rows is None:
        orders_rows = [{'amount': '300.00'}]
    queue = [otherpay_rows, orders_rows]

    class FakeSelf:
        def __init__(self):
            self._easypay_admin_utr = admin_utr
            self.logger = MagicMock()
            self.query_calls = []

        async def query(self, sql, *args):
            self.query_calls.append((sql, args))
            return queue.pop(0) if queue else []

    return FakeSelf()


def _call(self_obj, **override):
    kwargs = dict(
        mer_id='167471414',
        code='S17762732848219673450',
        mc_key='SmMTRADER',
        mc_key2='aa5225027e73d404caf7980fcb00560e',
        query_url='1',  # 生产垃圾值
        third_party_name='easypay',
    )
    kwargs.update(override)
    return asyncio.run(query_easypay_order(self_obj, **kwargs))


def make_response(text, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


# ---------------------------------------------------------------------------
# 1. 手机号归一化
# ---------------------------------------------------------------------------
class NormMsisdnTests(unittest.TestCase):
    def test_normalizes_pk_formats(self):
        canonical = '3145567308'
        cases = [
            '03145567308',
            '3145567308',
            '+923145567308',
            '923145567308',
            '0092-3145-567-308',
            ' 0314 556 7308 ',
        ]
        for raw in cases:
            with self.subTest(raw=raw):
                self.assertEqual(_easypay_norm_msisdn(raw), canonical)

    def test_empty_returns_empty(self):
        self.assertEqual(_easypay_norm_msisdn(''), '')
        self.assertEqual(_easypay_norm_msisdn(None), '')
        self.assertEqual(_easypay_norm_msisdn('   '), '')


# ---------------------------------------------------------------------------
# 2. XML 构造 & 解析
# ---------------------------------------------------------------------------
class BuildAndParseXmlTests(unittest.TestCase):
    def test_build_escapes_special_chars(self):
        xml = _easypay_build_inquire_xml(
            username='user&admin',
            password='pwd<>"\'',
            order_id='ORD1',
            account_num='ACC1',
        )
        self.assertIn('user&amp;admin', xml)
        self.assertIn('&lt;', xml)
        self.assertIn('&gt;', xml)
        self.assertIn('&quot;', xml)
        self.assertIn('&apos;', xml)
        self.assertIn('<orderId>ORD1</orderId>', xml)
        self.assertIn('<accountNum>ACC1</accountNum>', xml)

    def test_parse_paid_fixture(self):
        result = _easypay_parse_inquire(FIX_PAID)
        self.assertEqual(result['responseCode'], '0000')
        self.assertEqual(result['transactionStatus'], 'PAID')
        self.assertEqual(result['msisdn'], '03145567308')
        self.assertEqual(result['transactionAmount'], '300.0')
        self.assertEqual(result['storeName'], 'SmM TRADER')

    def test_parse_not_found_fixture(self):
        result = _easypay_parse_inquire(FIX_NOT_FOUND)
        self.assertEqual(result['responseCode'], '0003')
        self.assertNotIn('msisdn', result)
        self.assertNotIn('transactionStatus', result)

    def test_parse_invalid_xml_returns_none(self):
        self.assertIsNone(_easypay_parse_inquire('not xml at all'))
        self.assertIsNone(_easypay_parse_inquire(''))


# ---------------------------------------------------------------------------
# 3. query_easypay_order 全链路
# ---------------------------------------------------------------------------
class QueryEasypayOrderTests(unittest.TestCase):

    # ---- 成功路径 ----
    def test_paid_and_all_match_returns_true(self):
        fake = build_fake_self()
        with patch('application.order.query_third_order_status.requests.post',
                   return_value=make_response(FIX_PAID)):
            self.assertTrue(_call(fake))
        self.assertEqual(
            fake._easypay_query_result['transactionId'],
            '149222628',
        )

    def test_amount_scale_301_equals_301_00(self):
        # 响应 300.0 vs orders_ds.amount 300.00 必须相等（Decimal 按值比较）
        fake = build_fake_self(orders_rows=[{'amount': '300.00'}])
        with patch('application.order.query_third_order_status.requests.post',
                   return_value=make_response(FIX_PAID)):
            self.assertTrue(_call(fake))

    def test_admin_utr_with_plus92_matches_response_with_leading_zero(self):
        # admin 填 "+923145567308"，响应 "03145567308"，归一化后都是 3145567308
        fake = build_fake_self(admin_utr='+923145567308')
        with patch('application.order.query_third_order_status.requests.post',
                   return_value=make_response(FIX_PAID)):
            self.assertTrue(_call(fake))

    # ---- 拒绝路径（False）----
    def test_transaction_status_failed_returns_false(self):
        fake = build_fake_self()
        with patch('application.order.query_third_order_status.requests.post',
                   return_value=make_response(FIX_FAILED)):
            self.assertFalse(_call(fake))

    def test_response_code_non_0000_returns_false(self):
        fake = build_fake_self()
        with patch('application.order.query_third_order_status.requests.post',
                   return_value=make_response(FIX_NOT_FOUND)):
            self.assertFalse(_call(fake))

    def test_msisdn_mismatch_returns_false(self):
        fake = build_fake_self(admin_utr='03145567308')
        with patch('application.order.query_third_order_status.requests.post',
                   return_value=make_response(FIX_MSISDN_MISMATCH)):
            self.assertFalse(_call(fake))

    def test_amount_mismatch_returns_false(self):
        fake = build_fake_self(orders_rows=[{'amount': '300.00'}])
        with patch('application.order.query_third_order_status.requests.post',
                   return_value=make_response(FIX_AMOUNT_MISMATCH)):
            self.assertFalse(_call(fake))

    def test_missing_msisdn_field_returns_false(self):
        fake = build_fake_self()
        with patch('application.order.query_third_order_status.requests.post',
                   return_value=make_response(FIX_NO_MSISDN)):
            self.assertFalse(_call(fake))

    def test_missing_transaction_amount_field_returns_false(self):
        fake = build_fake_self()
        with patch('application.order.query_third_order_status.requests.post',
                   return_value=make_response(FIX_NO_AMOUNT)):
            self.assertFalse(_call(fake))

    def test_admin_utr_empty_returns_false_without_network_call(self):
        fake = build_fake_self(admin_utr='')
        with patch('application.order.query_third_order_status.requests.post') as mock_post:
            self.assertFalse(_call(fake))
            mock_post.assert_not_called()

    # ---- 不确定路径（None）----
    def test_otherpay_missing_returns_none(self):
        fake = build_fake_self(otherpay_rows=[])
        with patch('application.order.query_third_order_status.requests.post') as mock_post:
            self.assertIsNone(_call(fake))
            mock_post.assert_not_called()

    def test_order_missing_returns_none(self):
        fake = build_fake_self(orders_rows=[])
        with patch('application.order.query_third_order_status.requests.post') as mock_post:
            self.assertIsNone(_call(fake))
            mock_post.assert_not_called()

    def test_http_status_500_returns_none(self):
        fake = build_fake_self()
        with patch('application.order.query_third_order_status.requests.post',
                   return_value=make_response('', status_code=500)):
            self.assertIsNone(_call(fake))

    def test_invalid_xml_response_returns_none(self):
        fake = build_fake_self()
        with patch('application.order.query_third_order_status.requests.post',
                   return_value=make_response('not xml at all')):
            self.assertIsNone(_call(fake))

    def test_request_exception_returns_none(self):
        import requests as real_requests
        fake = build_fake_self()
        with patch('application.order.query_third_order_status.requests.post',
                   side_effect=real_requests.ConnectionError('boom')):
            self.assertIsNone(_call(fake))


if __name__ == '__main__':
    unittest.main()
