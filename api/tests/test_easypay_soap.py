import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class EasypaySoapXmlTests(unittest.TestCase):
    """测试 SOAP XML 构造（正确命名空间来自 WSDL 解析）"""

    def test_build_initiate_xml_contains_correct_namespace(self):
        from application.pay.easypay_soap import build_initiate_xml

        xml = build_initiate_xml(
            username='SmMTRADER',
            password='abc123',
            order_id='ORD-001',
            store_id='1257141',
            amount=100.00,
            mobile_number='03188711901',
            email='test@example.com',
        )
        # 正确的命名空间
        self.assertIn('xmlns:ns0="http://dto.transaction.partner.pg.systems.com/"', xml)
        self.assertIn('xmlns:ns1="http://dto.common.pg.systems.com/"', xml)
        self.assertIn('xmlns:ns2="http://dto.common.pg.systems.com/"', xml)
        self.assertIn('initiateTransactionRequestType', xml)

    def test_build_initiate_xml_contains_all_fields(self):
        from application.pay.easypay_soap import build_initiate_xml

        xml = build_initiate_xml(
            username='SmMTRADER',
            password='abc123',
            order_id='ORD-001',
            store_id='1257141',
            amount=100.00,
            mobile_number='03188711901',
            email='test@example.com',
        )
        self.assertIn('SmMTRADER</ns1:username>', xml)
        self.assertIn('abc123</ns2:password>', xml)
        self.assertIn('<orderId>ORD-001</orderId>', xml)
        self.assertIn('<storeId>1257141</storeId>', xml)
        self.assertIn('<transactionAmount>100.00</transactionAmount>', xml)
        self.assertIn('<transactionType>MA</transactionType>', xml)
        self.assertIn('<msisdn>03188711901</msisdn>', xml)
        self.assertIn('<mobileAccountNo>03188711901</mobileAccountNo>', xml)

    def test_build_initiate_xml_escapes_special_chars(self):
        from application.pay.easypay_soap import build_initiate_xml

        xml = build_initiate_xml(
            username='user<>&"',
            password='pass',
            order_id='ORD-001',
            store_id='123',
            amount=10.00,
            mobile_number='03188711901',
            email='test@example.com',
        )
        self.assertIn('user&lt;&gt;&amp;"', xml)
        self.assertNotIn('user<>&"', xml)


class EasypaySoapParseTests(unittest.TestCase):
    """测试 SOAP XML 响应解析"""

    INITIATE_SUCCESS_RESPONSE = '''<?xml version="1.0" encoding="UTF-8"?>
    <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
      <soap:Body>
        <ns2:initiateTransactionResponse xmlns:ns2="http://partner.transaction.easypaisa.telenor.com.pk/">
          <responseCode>0000</responseCode>
          <orderId>ORD-001</orderId>
          <storeId>1257141</storeId>
          <transactionId>TXN-12345</transactionId>
          <transactionDateTime>20260401120000</transactionDateTime>
          <paymentToken>TOKEN-ABC</paymentToken>
          <paymentTokenExiryDateTime>20260402120000</paymentTokenExiryDateTime>
        </ns2:initiateTransactionResponse>
      </soap:Body>
    </soap:Envelope>'''

    INITIATE_FAIL_RESPONSE = '''<?xml version="1.0" encoding="UTF-8"?>
    <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
      <soap:Body>
        <ns2:initiateTransactionResponse xmlns:ns2="http://partner.transaction.easypaisa.telenor.com.pk/">
          <responseCode>0001</responseCode>
        </ns2:initiateTransactionResponse>
      </soap:Body>
    </soap:Envelope>'''

    INQUIRE_SUCCESS_RESPONSE = '''<?xml version="1.0" encoding="UTF-8"?>
    <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
      <soap:Body>
        <ns2:inquireTransactionResponse xmlns:ns2="http://partner.transaction.easypaisa.telenor.com.pk/">
          <transactionStatus>PAID</transactionStatus>
          <transactionId>TXN-67890</transactionId>
          <responseCode>0000</responseCode>
          <orderId>ORD-001</orderId>
        </ns2:inquireTransactionResponse>
      </soap:Body>
    </soap:Envelope>'''

    def test_parse_initiate_success(self):
        from application.pay.easypay_soap import parse_initiate_response
        result = parse_initiate_response(self.INITIATE_SUCCESS_RESPONSE)
        self.assertTrue(result['success'])
        self.assertEqual(result['response_code'], '0000')
        self.assertEqual(result['order_id'], 'ORD-001')
        self.assertEqual(result['transaction_id'], 'TXN-12345')

    def test_parse_initiate_failure(self):
        from application.pay.easypay_soap import parse_initiate_response
        result = parse_initiate_response(self.INITIATE_FAIL_RESPONSE)
        self.assertFalse(result['success'])
        self.assertEqual(result['response_code'], '0001')

    def test_parse_initiate_malformed_xml(self):
        from application.pay.easypay_soap import parse_initiate_response
        result = parse_initiate_response('not xml at all')
        self.assertFalse(result['success'])
        self.assertIn('error', result)

    def test_parse_inquire_success(self):
        from application.pay.easypay_soap import parse_inquire_response

        result = parse_inquire_response(self.INQUIRE_SUCCESS_RESPONSE)

        self.assertEqual(result['transaction_status'], 'PAID')
        self.assertEqual(result['transaction_id'], 'TXN-67890')
        self.assertEqual(result['response_code'], '0000')
        self.assertEqual(result['order_id'], 'ORD-001')

    def test_parse_inquire_malformed_xml(self):
        from application.pay.easypay_soap import parse_inquire_response

        result = parse_inquire_response('not xml at all')

        self.assertIn('error', result)


class EasypaySoapAsyncTests(unittest.TestCase):
    """测试异步发起交易"""

    def test_async_initiate_success(self):
        from application.pay.easypay_soap import async_initiate_transaction

        mock_response_xml = EasypaySoapParseTests.INITIATE_SUCCESS_RESPONSE

        async def run():
            with patch('application.pay.easypay_soap.aiohttp.ClientSession') as mock_session_cls, \
                    patch('application.pay.easypay_soap.logger') as mock_logger:
                mock_resp = AsyncMock()
                mock_resp.status = 200
                mock_resp.text = AsyncMock(return_value=mock_response_xml)
                mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
                mock_resp.__aexit__ = AsyncMock(return_value=False)

                mock_session = AsyncMock()
                mock_session.post = MagicMock(return_value=mock_resp)
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=False)
                mock_session_cls.return_value = mock_session

                result = await async_initiate_transaction(
                    soap_url='https://fake.endpoint',
                    username='SmMTRADER',
                    password='abc123',
                    order_id='ORD-001',
                    store_id='1257141',
                    amount=100.00,
                    mobile_number='03188711901',
                    email='test@example.com',
                )
                self.assertTrue(result['success'])
                self.assertEqual(result['order_id'], 'ORD-001')
                mock_logger.info.assert_called_once()
                self.assertIn('原始响应', mock_logger.info.call_args[0][0])
                self.assertIn(mock_response_xml, mock_logger.info.call_args[0][0])

        asyncio.run(run())

    def test_async_initiate_network_error(self):
        from application.pay.easypay_soap import async_initiate_transaction

        async def run():
            with patch('application.pay.easypay_soap.aiohttp.ClientSession') as mock_session_cls, \
                    patch('application.pay.easypay_soap.logger') as mock_logger:
                mock_session = AsyncMock()
                mock_session.post = MagicMock(side_effect=aiohttp.ClientError('connection failed'))
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=False)
                mock_session_cls.return_value = mock_session

                result = await async_initiate_transaction(
                    soap_url='https://fake.endpoint',
                    username='u', password='p',
                    order_id='ORD-001', store_id='123',
                    amount=10.00, mobile_number='031',
                    email='t@t.com',
                )
                self.assertFalse(result['success'])
                self.assertIn('error', result)
                mock_logger.exception.assert_called_once()
                self.assertIn('请求异常', mock_logger.exception.call_args[0][0])

        asyncio.run(run())

    def test_async_inquire_success(self):
        from application.pay.easypay_soap import async_inquire_transaction

        mock_response_xml = EasypaySoapParseTests.INQUIRE_SUCCESS_RESPONSE

        async def run():
            with patch('application.pay.easypay_soap.aiohttp.ClientSession') as mock_session_cls, \
                    patch('application.pay.easypay_soap.logger') as mock_logger:
                mock_resp = AsyncMock()
                mock_resp.status = 200
                mock_resp.text = AsyncMock(return_value=mock_response_xml)
                mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
                mock_resp.__aexit__ = AsyncMock(return_value=False)

                mock_session = AsyncMock()
                mock_session.post = MagicMock(return_value=mock_resp)
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=False)
                mock_session_cls.return_value = mock_session

                result = await async_inquire_transaction(
                    soap_url='https://fake.endpoint',
                    username='SmMTRADER',
                    password='abc123',
                    order_id='ORD-001',
                    account_num='M-123',
                )

                self.assertEqual(result['transaction_id'], 'TXN-67890')
                self.assertEqual(result['order_id'], 'ORD-001')
                mock_logger.info.assert_called_once()
                self.assertIn('inquireTransaction 原始响应', mock_logger.info.call_args[0][0])
                self.assertIn(mock_response_xml, mock_logger.info.call_args[0][0])

        asyncio.run(run())

    def test_build_inquire_xml_contains_all_fields(self):
        from application.pay.easypay_soap import build_inquire_xml

        xml = build_inquire_xml(
            username='SmMTRADER',
            password='abc123',
            order_id='ORD-001',
            account_num='M-123',
        )

        self.assertIn('inquireTransactionRequestType', xml)
        self.assertIn('SmMTRADER</ns1:username>', xml)
        self.assertIn('abc123</ns2:password>', xml)
        self.assertIn('<orderId>ORD-001</orderId>', xml)
        self.assertIn('<accountNum>M-123</accountNum>', xml)


if __name__ == '__main__':
    unittest.main()
