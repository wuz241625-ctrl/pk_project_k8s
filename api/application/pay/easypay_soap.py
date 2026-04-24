"""
Easypay SOAP API — XML 构造、请求发送、响应解析

initiateTransaction 是同步阻塞调用：发起后等待用户在 App 确认付款才返回。
使用 aiohttp 异步发送避免阻塞主线程，timeout 设 90 秒。
"""
import logging
import xml.sax.saxutils
import xml.etree.ElementTree as ET

import aiohttp

logger = logging.getLogger(__name__)


def _esc(value):
    """XML 特殊字符转义"""
    return xml.sax.saxutils.escape(str(value))


def build_initiate_xml(username, password, order_id, store_id, amount,
                       mobile_number, email):
    """构造 initiateTransaction SOAP XML（命名空间来自 WSDL 解析）"""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<soap-env:Envelope xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/">'
        '<soap-env:Body>'
        '<ns0:initiateTransactionRequestType'
        ' xmlns:ns0="http://dto.transaction.partner.pg.systems.com/">'
        f'<ns1:username xmlns:ns1="http://dto.common.pg.systems.com/">'
        f'{_esc(username)}</ns1:username>'
        f'<ns2:password xmlns:ns2="http://dto.common.pg.systems.com/">'
        f'{_esc(password)}</ns2:password>'
        f'<orderId>{_esc(order_id)}</orderId>'
        f'<storeId>{_esc(store_id)}</storeId>'
        f'<transactionAmount>{float(amount):.2f}</transactionAmount>'
        '<transactionType>MA</transactionType>'
        f'<msisdn>{_esc(mobile_number)}</msisdn>'
        f'<mobileAccountNo>{_esc(mobile_number)}</mobileAccountNo>'
        f'<emailAddress>{_esc(email)}</emailAddress>'
        '</ns0:initiateTransactionRequestType>'
        '</soap-env:Body>'
        '</soap-env:Envelope>'
    )


def _find_text(root, tag_name):
    """在 XML 树中搜索指定标签，忽略命名空间"""
    for elem in root.iter():
        local_name = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        if local_name == tag_name:
            return elem.text
    return None


def parse_initiate_response(xml_text):
    """解析 initiateTransaction 响应"""
    try:
        root = ET.fromstring(xml_text)
        code = _find_text(root, 'responseCode')
        return {
            'success': code == '0000',
            'response_code': code,
            'order_id': _find_text(root, 'orderId'),
            'store_id': _find_text(root, 'storeId'),
            'transaction_id': _find_text(root, 'transactionId'),
            'transaction_datetime': _find_text(root, 'transactionDateTime'),
            'payment_token': _find_text(root, 'paymentToken'),
            'token_expiry': _find_text(root, 'paymentTokenExiryDateTime'),
        }
    except ET.ParseError as e:
        return {'success': False, 'error': str(e)}


SOAP_HEADERS = {'Content-Type': 'text/xml; charset=utf-8'}


async def async_initiate_transaction(soap_url, username, password, order_id,
                                     store_id, amount, mobile_number, email,
                                     timeout_seconds=90):
    """异步发起 MA 交易（同步阻塞式，等待用户在 App 确认付款后返回）"""
    xml_body = build_initiate_xml(username, password, order_id, store_id,
                                  amount, mobile_number, email)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(soap_url, data=xml_body,
                                    headers=SOAP_HEADERS,
                                    timeout=aiohttp.ClientTimeout(
                                        total=timeout_seconds)) as resp:
                text = await resp.text()
                logger.info(f'[easypay] SOAP initiateTransaction 原始响应, order_id={order_id}: {text}')
                return parse_initiate_response(text)
    except Exception as e:
        logger.exception(f'[easypay] SOAP initiateTransaction 请求异常, order_id={order_id}: {e}')
        return {'success': False, 'error': str(e)}


def build_inquire_xml(username, password, order_id, account_num):
    """构造 inquireTransaction SOAP XML"""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<soap-env:Envelope xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/">'
        '<soap-env:Body>'
        '<ns0:inquireTransactionRequestType'
        ' xmlns:ns0="http://dto.transaction.partner.pg.systems.com/">'
        f'<ns1:username xmlns:ns1="http://dto.common.pg.systems.com/">'
        f'{_esc(username)}</ns1:username>'
        f'<ns2:password xmlns:ns2="http://dto.common.pg.systems.com/">'
        f'{_esc(password)}</ns2:password>'
        f'<orderId>{_esc(order_id)}</orderId>'
        f'<accountNum>{_esc(account_num)}</accountNum>'
        '</ns0:inquireTransactionRequestType>'
        '</soap-env:Body>'
        '</soap-env:Envelope>'
    )


def parse_inquire_response(xml_text):
    """解析 inquireTransaction 响应"""
    try:
        root = ET.fromstring(xml_text)
        return {
            'transaction_status': _find_text(root, 'transactionStatus'),
            'transaction_id': _find_text(root, 'transactionId'),
            'response_code': _find_text(root, 'responseCode'),
            'order_id': _find_text(root, 'orderId'),
        }
    except ET.ParseError as e:
        return {'error': str(e)}


async def async_inquire_transaction(soap_url, username, password, order_id,
                                    account_num, timeout_seconds=30):
    """异步查询交易详情"""
    xml_body = build_inquire_xml(username, password, order_id, account_num)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(soap_url, data=xml_body,
                                    headers=SOAP_HEADERS,
                                    timeout=aiohttp.ClientTimeout(
                                        total=timeout_seconds)) as resp:
                text = await resp.text()
                logger.info(f'[easypay] SOAP inquireTransaction 原始响应, order_id={order_id}: {text}')
                return parse_inquire_response(text)
    except Exception as e:
        logger.exception(f'[easypay] SOAP inquireTransaction 请求异常, order_id={order_id}: {e}')
        return {'error': str(e)}
