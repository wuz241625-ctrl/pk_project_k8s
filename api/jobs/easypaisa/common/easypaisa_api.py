import uuid
import json
import base64
import hashlib
import time
import logging
import aiohttp


class AccountInvalidError(Exception):
    """API 返回 501，账号无效，需要立即下线"""
    pass


class EasyPaisaAPI:
    """EasyPaisa API 统一封装"""

    def __init__(self, api_url: str, user_id: str, secret_key: str, logger: logging.Logger = None):
        self.api_url = api_url
        self.user_id = user_id
        self.secret_key = secret_key
        self.logger = logger or logging.getLogger(__name__)

    def _sign_request(self, payload: dict) -> dict:
        payload_str = json.dumps(payload, separators=(',', ':'))
        data_b64 = base64.b64encode(payload_str.encode('utf-8')).decode('utf-8')
        sign = hashlib.md5((data_b64 + self.secret_key).encode('utf-8')).hexdigest()
        return {'user_id': self.user_id, 'data': data_b64, 'sign': sign}

    def _build_payload(self, action: str, payload_data: dict) -> dict:
        return {"id": str(uuid.uuid4()), "action": action, "payload": payload_data}

    async def _post(self, payload: dict, timeout: int = 30) -> dict | None:
        form_data = self._sign_request(payload)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url, data=form_data,
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as response:
                    if response.status != 200:
                        self.logger.error(f"HTTP错误: {response.status}")
                        return None
                    content_type = response.headers.get('Content-Type', '')
                    if 'application/json' not in content_type:
                        self.logger.error(f"非JSON响应: Content-Type={content_type}")
                        return None
                    return await response.json()
        except (aiohttp.ClientError, TimeoutError) as e:
            self.logger.error(f"请求异常: {e}")
            return None

    def _check_501(self, result: dict, context: str = ""):
        if result and result.get('code') == 501:
            msg = result.get('msg', result.get('message', '账号无效(501)'))
            raise AccountInvalidError(f"{context}: {msg}")

    async def query_bill(self, phone: str, accno: str, timeout: int = 30) -> dict:
        payload = self._build_payload("queryBill", {"account_id": phone, "accno": accno})
        result = await self._post(payload, timeout=timeout)
        if result is None:
            return {'success': False, 'error': 'API无响应或网络错误'}
        self._check_501(result, f"queryBill phone={phone}")
        if result.get('code') != 200:
            return {
                'success': False,
                'error_code': result.get('code'),
                'error': result.get('msg', 'API返回错误'),
                'data': result
            }
        transactions = result.get('data', {}).get('body', {}).get('transactionHistory', [])
        return {'success': True, 'transaction_history_list': transactions, 'data': result}

    async def query_balance(self, phone: str, accno: str, timeout: int = 30) -> dict:
        payload = self._build_payload("queryBalance", {"account_id": phone, "accno": accno})
        start = time.time()
        result = await self._post(payload, timeout=timeout)
        response_time = time.time() - start
        if result is None:
            return {'success': False, 'error': 'API无响应', 'response_time': response_time}
        self._check_501(result, f"queryBalance phone={phone}")
        if result.get('code') != 200:
            return {
                'success': False,
                'error_code': result.get('code'),
                'error': result.get('msg', 'API返回错误'),
                'response_time': response_time,
                'data': result,
                'should_retry': result.get('code') == 423
            }
        data = result.get('data', {})
        body = data.get('body', {}) if isinstance(data, dict) else {}
        balance = body.get('totalbalance', result.get('totalbalance', result.get('balance', 0)))
        return {'success': True, 'balance': balance, 'response_time': response_time, 'data': result}

    async def query_limits(self, phone: str, accno: str, timeout: int = 30) -> dict:
        payload = self._build_payload("queryLimits", {"account_id": phone, "accno": accno})
        result = await self._post(payload, timeout=timeout)
        if result is None:
            return {'success': False, 'error': 'API无响应'}
        self._check_501(result, f"queryLimits phone={phone}")
        if result.get('code') != 200:
            return {'success': False, 'error_code': result.get('code'), 'error': result.get('msg', 'API返回错误'), 'data': result}
        limits_data = result.get('data', {}).get('body', {})
        return {'success': True, 'limits': limits_data, 'data': result}

    async def transfer(self, phone: str, accno: str, to_account: str, amount: str,
                       bankcode: str = '', remark: str = '', timeout: int = 60) -> dict:
        if bankcode:
            action = "transferToCard"
            payload_data = {
                "account_id": phone, "from_accno": accno,
                "bankcode": bankcode, "to_accno": to_account,
                "amount": amount, "remark": remark
            }
        else:
            action = "transferToAcc"
            payload_data = {
                "account_id": phone, "from_accno": accno,
                "to_accno": to_account, "amount": amount, "remark": remark
            }
        payload = self._build_payload(action, payload_data)
        start = time.time()
        result = await self._post(payload, timeout=timeout)
        response_time = time.time() - start
        if result is None:
            return {'success': False, 'error': 'API无响应', 'response_time': response_time}
        self._check_501(result, f"transfer phone={phone}")
        code = result.get('code')
        return {
            'success': code == 200,
            'code': code,
            'msg': result.get('msg', ''),
            'data': result.get('data', {}),
            'response_time': response_time,
            'raw': result
        }
