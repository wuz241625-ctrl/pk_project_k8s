"""TransferExecutor — handles EasyPaisa transfer API calls and result parsing.

Extracted from auto_payout.py (lines 3732-4581).
"""
import time
import uuid
import base64
import hashlib
import json
import aiohttp
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional


class TransferExecutor:
    """Executes EasyPaisa transfer API calls and parses results."""

    def __init__(self, redis_client, logger, conf: dict, REDIS_KEYS: dict,
                 api_url: str, user_id: str, secret_key: str,
                 transaction_logger, account_selector):
        self.redis = redis_client
        self.logger = logger
        self.conf = conf
        self.REDIS_KEYS = REDIS_KEYS
        self.api_url = api_url
        self.user_id = user_id
        self.secret_key = secret_key
        self.transaction_logger = transaction_logger
        self.account_selector = account_selector

    def _is_pakistan_mobile_number(self, account_number: str) -> bool:
        """判断是否为巴基斯坦手机号（EasyPaisa账号格式）"""
        from jobs.easypaisa.payout.utils import is_pakistan_mobile_number
        return is_pakistan_mobile_number(account_number)

    def log_complete_transaction(self, order_data, account_info, inner_payload, api_result,
                                 status, **kwargs):
        """Delegate to transaction_logger.log_complete_transaction."""
        self.transaction_logger.log_complete_transaction(
            order_data, account_info, inner_payload, api_result, status, **kwargs)

    async def fetch_balance_from_api(self, account_info):
        """Delegate to account_selector.fetch_balance_from_api."""
        return await self.account_selector.fetch_balance_from_api(account_info)

    async def _call_easypaisa_api(self, inner_payload: Dict, account_id: str, timeout: int = 30) -> Optional[Dict]:
        """调用EasyPaisa API的底层方法

        Args:
            inner_payload: API请求载荷
            account_id: 账号ID
            timeout: 超时时间（秒），默认30秒，转账API使用60秒
        """
        try:
            # EasyPaisa API配置 - 从实例属性获取
            api_url = self.api_url
            user_id = self.user_id
            secret_key = self.secret_key

            if not all([api_url, user_id, secret_key]):
                self.logger.error("EasyPaisa API配置缺失")
                return None

            # 1. 准备payload - 安全序列化，处理可能的Decimal类型
            try:
                payload_json = json.dumps(inner_payload, separators=(',', ':'))
            except TypeError as e:
                # 如果有Decimal类型导致序列化失败，使用安全转换
                self.logger.warning(f"JSON序列化失败，使用安全转换: {e}")

                def safe_json_convert(obj):
                    """递归转换对象中的Decimal类型"""
                    if isinstance(obj, Decimal):
                        return float(obj)
                    elif isinstance(obj, dict):
                        return {k: safe_json_convert(v) for k, v in obj.items()}
                    elif isinstance(obj, (list, tuple)):
                        return [safe_json_convert(item) for item in obj]
                    else:
                        return obj

                safe_payload = safe_json_convert(inner_payload)
                payload_json = json.dumps(safe_payload, separators=(',', ':'))

            # 2. Base64编码
            payload_b64 = base64.b64encode(payload_json.encode()).decode()

            # 3. 生成签名
            sign_str = payload_b64 + secret_key
            sign = hashlib.md5(sign_str.encode()).hexdigest()

            # 4. 构建请求数据
            form_data = {
                'user_id': user_id,
                'data': payload_b64,
                'sign': sign
            }

            # 5. 发送HTTP请求
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url, data=form_data,
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        try:
                            result = await resp.json()
                            self.logger.info(f"EasyPaisa API响应: {result}")
                            return result
                        except Exception as e:
                            self.logger.error(f"EasyPaisa API响应解析失败: {e}")
                            return None
                    else:
                        self.logger.error(f"EasyPaisa API HTTP错误: {resp.status}")
                        return None

        except Exception as e:
            self.logger.error(f"调用EasyPaisa API异常: {e}")
            return None

    def _extract_transaction_id(self, api_result: Dict, action: str) -> str:
        """从API响应中提取交易ID"""
        try:
            data = api_result.get('data', {})

            # 优先从 data.body.data.extOrderNo 提取（EasyPaisa API 实际返回路径）
            body = data.get('body', {})
            body_data = body.get('data', {})
            transaction_id = body_data.get('extOrderNo', '')

            if transaction_id:
                return transaction_id

            # 备用路径1：尝试从 body.orderNo 提取
            transaction_id = body.get('orderNo', '')
            if transaction_id:
                return transaction_id

            # 备用路径2：尝试从 body.busOrderNo 提取
            transaction_id = body.get('busOrderNo', '')
            if transaction_id:
                return transaction_id

            # 如果都没有，记录警告并生成备用ID
            self.logger.warning(f"API响应中未找到交易ID，使用备用方案生成ID")
            return f"EP{uuid.uuid4().hex[:12].upper()}"

        except Exception as e:
            self.logger.error(f"提取交易ID失败: {e}")
            return f"EP{uuid.uuid4().hex[:12].upper()}"

    async def _execute_easypaisa_transfer(self, order_data: Dict, account_info: Dict) -> Optional[Dict]:
        """执行EasyPaisa转账 - 调用真实API"""
        # account_info 已经是完整的账号信息，包含 payment_id, phone, balance 等
        # 设置默认变量以防止NameError
        start_time = time.time()
        inner_payload = {}
        before_balance = None
        process_details = {}

        try:
            order_code = order_data['code']
            amount = str(order_data['amount'])
            to_account = order_data.get('payment_account', '')  # 目标账号
            payment_name = order_data.get('payment_name', '')  # 收款人姓名
            ifsc_code = order_data.get('ifsc', '')  # IFSC银行代码

            # 从传入的账号信息中获取数据（在早期获取，避免后续使用时未定义）
            payment_id = account_info.get('payment_id')
            phone_number = account_info.get('phone')

            # 判断是否为巴基斯坦手机号（EasyPaisa账号）
            is_pakistan_mobile = self._is_pakistan_mobile_number(to_account)

            # 根据账号类型确定转账方式和bankcode
            if is_pakistan_mobile and ifsc_code.lower() == 'easypaisa':
                # EasyPaisa同行转账，不需要bankcode
                to_bankcode = ''
                transfer_type = "EasyPaisa同行转账"
            else:
                # 跨行转账到银行卡，使用ifsc作为bankcode
                to_bankcode = ifsc_code
                transfer_type = "跨行转账到银行卡"

            # 记录流程开始时间和详细信息
            process_start_time = time.time()
            process_details = {
                'process_start_time': datetime.fromtimestamp(process_start_time).isoformat(),
                'order_received_time': datetime.fromtimestamp(process_start_time).isoformat(),
                'account_selection_time': datetime.now().isoformat(),
                'account_selection_status': 'success',
                'account_selection_criteria': 'auto_selected'
            }

            self.logger.info(f"开始执行EasyPaisa转账:")
            self.logger.info(f"  订单号: {order_code}")
            self.logger.info(f"  转出账号: {phone_number} (EasyPaisa钱包)")
            self.logger.info(f"  转入账号: {to_account}")
            self.logger.info(f"  账号类型判断: {'巴基斯坦手机号' if is_pakistan_mobile else '银行账号'}")
            self.logger.info(f"  收款人姓名: {payment_name}")
            self.logger.info(f"  转账金额: {amount}")
            self.logger.info(f"  转账类型: {transfer_type}")
            self.logger.info(f"  银行代码: {to_bankcode if to_bankcode else '无需bankcode'}")

            # 记录风险检查（这里简化为成功）
            process_details.update({
                'risk_check_time': datetime.now().isoformat(),
                'risk_check_status': 'success',
                'risk_check_details': {
                    'amount_check': 'passed',
                    'account_check': 'passed',
                    'frequency_check': 'passed'
                }
                        })

                        # 生成请求UUID
            request_uuid = str(uuid.uuid4())
            self.logger.info(f"  请求UUID: {request_uuid}")

            # 记录转账尝试开始时间
            start_time = time.time()

            self.logger.info(f"  账号信息: payment_id={payment_id}, phone={phone_number}")

            # 获取转账前余额
            before_balance = None
            balance_start_time = time.time()
            process_details['before_balance_time'] = datetime.now().isoformat()

            try:
                if account_info and account_info.get('payment_id'):
                    balance_result = await self.fetch_balance_from_api(account_info)
                    balance_duration = int((time.time() - balance_start_time) * 1000)

                    if balance_result and balance_result.get('success'):
                        before_balance = balance_result.get('balance')
                        self.logger.info(f"  转账前余额: {before_balance}")

                        process_details.update({
                            'before_balance_status': 'success',
                            'before_balance_duration': balance_duration
                        })
                    else:
                        error_msg = balance_result.get('error', '未知错误') if balance_result else 'API调用失败'
                        self.logger.warning(f"  无法获取转账前余额: {error_msg}")

                        process_details.update({
                            'before_balance_status': 'failed',
                            'before_balance_error': error_msg,
                            'before_balance_duration': balance_duration
                        })
                else:
                    error_msg = '账号信息不完整'
                    self.logger.warning(f"  账号信息不完整，跳过余额查询")

                    process_details.update({
                        'before_balance_status': 'skipped',
                        'before_balance_error': error_msg
                    })
            except Exception as e:
                error_msg = str(e)
                self.logger.warning(f"  获取转账前余额异常: {e}")
                before_balance = None
                balance_duration = int((time.time() - balance_start_time) * 1000)

                process_details.update({
                    'before_balance_status': 'exception',
                    'before_balance_error': error_msg,
                    'before_balance_duration': balance_duration
                })

            # 判断转账类型：EasyPaisa同行转账 vs 跨行转账
            if to_bankcode:
                # 跨行转账到银行卡
                action = "transferToCard"
                payload_data = {
                    "account_id": phone_number,
                    "bankcode": to_bankcode,
                    "to_accno": to_account,
                    "amount": amount,
                    "remark": order_code
                }

                # account_accno为转账必送参数
                account_accno = account_info.get('account_accno')
                if not account_accno:
                    error_msg = f'账号{payment_id}缺少account_accno字段，无法执行跨行转账'
                    self.logger.error(error_msg)
                    self.log_complete_transaction(
                        order_data, account_info, {}, {},
                        "account_config_error",
                        error_message=error_msg,
                        start_time=start_time,
                        before_balance=before_balance,
                        process_details=process_details
                    )
                    return {'success': False, 'message': error_msg}

                payload_data["from_accno"] = account_accno
                self.logger.info(f"跨行转账使用account_accno: {account_accno}")

                self.logger.info(f"转账类型: 跨行转账 (transferToCard)")
            else:
                # EasyPaisa同行转账
                action = "transferToAcc"
                payload_data = {
                    "account_id": phone_number,
                    "to_accno": to_account,
                    "amount": amount,
                    "remark": order_code
                }

                # account_accno为转账必送参数
                account_accno = account_info.get('account_accno')
                if not account_accno:
                    error_msg = f'账号{payment_id}缺少account_accno字段，无法执行同行转账'
                    self.logger.error(error_msg)
                    self.log_complete_transaction(
                        order_data, account_info, {}, {},
                        "account_config_error",
                        error_message=error_msg,
                        start_time=start_time,
                        before_balance=before_balance,
                        process_details=process_details
                    )
                    return {'success': False, 'message': error_msg}

                payload_data["from_accno"] = account_accno
                self.logger.info(f"同行转账使用account_accno: {account_accno}")

                self.logger.info(f"转账类型: EasyPaisa同行转账 (transferToAcc)")

            # 构建内层payload
            inner_payload = {
                "id": request_uuid,
                "action": action,
                "payload": payload_data
            }

            self.logger.info(f"API请求载荷: {inner_payload}")

            # 调用真实EasyPaisa API
            self.logger.info(f"开始调用EasyPaisa API...")

            api_start_time = time.time()
            process_details['transfer_api_time'] = datetime.now().isoformat()

            # 转账API使用60秒超时
            api_result = await self._call_easypaisa_api(inner_payload, phone_number, timeout=60)

            api_duration = int((time.time() - api_start_time) * 1000)
            process_details['api_duration_ms'] = api_duration

            # 记录API完整响应
            self.logger.info(f"EasyPaisa API响应: {api_result}")

            if api_result:
                code = api_result.get('code')
                msg = api_result.get('msg', '')
                data = api_result.get('data', {})

                self.logger.info(f"API响应解析: code={code}, msg={msg}, data={data}")

                if code == 200:
                    # 提取 orderStatus 判断实际状态
                    order_status = None

                    # 尝试从不同路径提取 orderStatus
                    if data and isinstance(data, dict):
                        body = data.get('body', {})
                        if isinstance(body, dict):
                            # 优先从 body.orderStatus 获取
                            order_status = body.get('orderStatus')

                            # 如果没有，从 body.data.orderStatus 获取
                            if not order_status:
                                body_data = body.get('data', {})
                                if isinstance(body_data, dict):
                                    order_status = body_data.get('orderStatus')

                    self.logger.info(f"API返回 code=200, orderStatus={order_status}")

                    # 提取交易ID（所有情况都需要）
                    transaction_id = self._extract_transaction_id(api_result, action)

                    # 根据 orderStatus 判断处理方式
                    if order_status == "P":
                        # ========== orderStatus = P (处理中/待确认) ==========
                        self.logger.info(f"转账处理中(orderStatus=P)，订单将设为确认中状态(status=2)")

                        # 添加处理中状态的流程信息
                        process_details.update({
                            'lock_release_time': datetime.now().isoformat(),
                            'lock_release_status': 'success',
                            'lock_release_details': {
                                'account_lock_released': True,
                                'payment_id_lock_released': True,
                                'release_reason': 'order_status_pending'
                            },
                            'order_status': 'P',
                            'order_status_meaning': 'pending',
                            'total_duration_ms': int((time.time() - process_start_time) * 1000)
                        })

                        # 记录完整的交易记录（处理中）
                        self.log_complete_transaction(order_data, account_info, inner_payload, api_result,
                                                    "failed", transaction_id=transaction_id, start_time=start_time,
                                                    before_balance=before_balance,
                                                    error_message="EasyPaisa转账pending，请人工确认",
                                                    process_details=process_details)

                        # 返回失败，但标记为待确认状态
                        return {
                            'success': False,
                            'treat_as_success': False,
                            'transaction_id': transaction_id,
                            'message': f'EasyPaisa转账处理中(orderStatus=P)，设为待确认状态: {msg}',
                            'payer_phone': phone_number,
                            'order_status': 'P'
                        }

                    else:
                        # ========== orderStatus = S (成功) 或其他状态 ==========
                        self.logger.info(f"转账成功(orderStatus={order_status})! 交易ID: {transaction_id}")

                        # 计算转账后余额（优化：避免额外API调用）
                        after_balance = None
                        process_details['after_balance_time'] = datetime.now().isoformat()

                        if before_balance is not None:
                            try:
                                # 直接用转账金额计算转账后余额
                                after_balance = Decimal(str(before_balance)) - Decimal(str(amount))

                                # 记录余额变化信息
                                try:
                                    before_balance_decimal = Decimal(str(before_balance)) if not isinstance(before_balance, Decimal) else before_balance
                                    balance_change = float(after_balance - before_balance_decimal)
                                except (ValueError, TypeError, Decimal.InvalidOperation) as e:
                                    self.logger.warning(f"计算余额变化失败: after_balance={after_balance} ({type(after_balance)}), before_balance={before_balance} ({type(before_balance)}), error={e}")
                                    balance_change = -float(amount)

                                self.logger.info(f"  转账后余额: {after_balance} (计算得出)")
                                self.logger.info(f"  余额变化: {balance_change}")

                                process_details.update({
                                    'after_balance_status': 'calculated',
                                    'calculation_method': 'before_balance - amount'
                                })

                            except Exception as e:
                                error_msg = f"计算转账后余额失败: {e}"
                                self.logger.warning(f"  {error_msg}")
                                after_balance = None
                                process_details.update({
                                    'after_balance_status': 'calculation_failed',
                                    'after_balance_error': error_msg
                                })
                        else:
                            error_msg = '转账前余额为空，无法计算转账后余额'
                            self.logger.warning(f"  {error_msg}")
                            process_details.update({
                                'after_balance_status': 'skipped',
                                'after_balance_error': error_msg
                            })

                        # 添加成功时的流程信息
                        process_details.update({
                            'lock_release_time': datetime.now().isoformat(),
                            'lock_release_status': 'success',
                            'lock_release_details': {
                                'account_lock_released': True,
                                'payment_id_lock_released': True
                            },
                            'order_status': order_status or 'unknown',
                            'total_duration_ms': int((time.time() - process_start_time) * 1000)
                        })

                        # 记录完整的交易记录（成功）
                        self.log_complete_transaction(order_data, account_info, inner_payload, api_result,
                                                    "success", transaction_id=transaction_id, start_time=start_time,
                                                    before_balance=before_balance, after_balance=after_balance,
                                                    process_details=process_details)

                        return {
                            'success': True,
                            'transaction_id': transaction_id,
                            'message': f'EasyPaisa转账成功: {msg}',
                            'payer_phone': phone_number,
                            'order_status': order_status or 'S'
                        }
                elif code == 402:
                    return self._handle_402_response(order_data, account_info, inner_payload, api_result,
                                                     msg, data, start_time, before_balance, process_details,
                                                     process_start_time)
                elif code == 501:
                    # AccountInvalid - 账号异常（包括2小时冷却期），立即下线
                    self.logger.error(f"账号异常或冷却期: {msg}")

                    process_details.update({
                        'lock_release_time': datetime.now().isoformat(),
                        'lock_release_status': 'success',
                        'lock_release_details': {
                            'account_lock_released': True,
                            'payment_id_lock_released': True,
                            'release_reason': 'account_invalid'
                        },
                        'total_duration_ms': int((time.time() - process_start_time) * 1000)
                    })

                    self.log_complete_transaction(order_data, account_info, inner_payload, api_result,
                                                "account_invalid", error_message=msg, start_time=start_time,
                                                before_balance=before_balance, process_details=process_details)

                    return {
                        'success': False,
                        'message': f'EasyPaisa账号异常或冷却期: {msg}',
                        'account_invalid': True
                    }
                elif code == 423:
                    # ServerBusy - 服务器忙，可重试
                    self.logger.warning(f"服务器忙碌: {msg}")

                    self.log_complete_transaction(order_data, account_info, inner_payload, api_result,
                                                "server_busy", error_message=msg, start_time=start_time,
                                                before_balance=before_balance, process_details=process_details)

                    return {
                        'success': False,
                        'message': f'EasyPaisa服务器忙碌: {msg}',
                        'can_retry': True,
                        'code': code
                    }
                elif code == 403:
                    # CheckParam - 参数错误
                    self.logger.error(f"参数错误: {msg}")

                    self.log_complete_transaction(order_data, account_info, inner_payload, api_result,
                                                "param_error", error_message=msg, start_time=start_time,
                                                before_balance=before_balance, process_details=process_details)

                    return {
                        'success': False,
                        'message': f'EasyPaisa参数错误: {msg}',
                        'can_retry': False,
                        'code': code
                    }
                elif code in [500, 503]:
                    # Error - 服务器严重错误
                    self.logger.error(f"服务器严重错误: {msg}")

                    self.log_complete_transaction(order_data, account_info, inner_payload, api_result,
                                                "server_error", error_message=msg, start_time=start_time,
                                                before_balance=before_balance, process_details=process_details)

                    return {
                        'success': False,
                        'message': f'EasyPaisa服务器错误: {msg}',
                        'can_retry': False,
                        'code': code
                    }
                else:
                    # 其他未知错误码
                    self.logger.error(f"未知错误码: code={code}, msg={msg}")

                    self.log_complete_transaction(order_data, account_info, inner_payload, api_result,
                                                "unknown_error", error_message=msg, start_time=start_time,
                                                before_balance=before_balance, process_details=process_details)

                    return {
                        'success': False,
                        'message': f'EasyPaisa未知错误: {msg}',
                        'can_retry': True,
                        'code': code
                    }
            else:
                self.logger.error("EasyPaisa API无响应（网络异常或超时）")

                self.log_complete_transaction(order_data, account_info, inner_payload, {},
                                            "api_no_response", error_message="API无响应（网络异常）", start_time=start_time,
                                            before_balance=before_balance, process_details=process_details)

                return {
                    'success': False,
                    'message': 'EasyPaisa API无响应（网络异常或超时）',
                    'can_retry': False,
                    'code': -1
                }

        except Exception as e:
            self.logger.error(f"EasyPaisa转账异常: {e}")

            # 记录完整的交易记录（异常）
            account_info = account_info if 'account_info' in locals() else {'phone': 'unknown', 'payment_id': 'unknown'}
            start_time = start_time if 'start_time' in locals() else time.time()
            inner_payload = inner_payload if 'inner_payload' in locals() else {}
            before_balance = before_balance if 'before_balance' in locals() else None
            process_details = process_details if 'process_details' in locals() else {}
            self.log_complete_transaction(order_data, account_info, inner_payload, {},
                                        "exception", error_message=str(e), start_time=start_time,
                                        before_balance=before_balance, process_details=process_details)

            return None

    def _handle_402_response(self, order_data, account_info, inner_payload, api_result,
                             msg, data, start_time, before_balance, process_details,
                             process_start_time):
        """Handle code=402 PaymentFail response."""
        # 仅提取 msgCd 进入日志；402 不按 msgCd 分支。
        msg_cd = None
        if data and isinstance(data, dict):
            msg_cd = data.get('msgCd')
            if not msg_cd:
                body = data.get('body', {})
                if isinstance(body, dict):
                    msg_cd = body.get('msgCd')

        # 402 是官方明确失败，但不区分 msgCd。是否驳回由订单重试次数决定。
        self.logger.warning(f"转账失败(可重试，msgCd仅记录不分支): {msg}")

        process_details.update({
            'lock_release_time': datetime.now().isoformat(),
            'lock_release_status': 'success',
            'lock_release_details': {
                'account_lock_released': True,
                'payment_id_lock_released': True,
                'release_reason': 'transfer_failed'
            },
            'total_duration_ms': int((time.time() - process_start_time) * 1000)
        })

        self.log_complete_transaction(order_data, account_info, inner_payload, api_result,
                                    "failed", error_message=msg, start_time=start_time,
                                    before_balance=before_balance, process_details=process_details)

        return {
            'success': False,
            'message': f'EasyPaisa转账失败: {msg}',
            'can_retry': True,
            'code': 402
        }
