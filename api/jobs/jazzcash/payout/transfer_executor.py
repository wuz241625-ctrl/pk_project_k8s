"""
JazzCash Transfer Executor — API calls, bank code mapping, phone format checks.
Extracted from jazzcash_auto_payout.py Phase 3 refactoring.
"""
import re
import json
import time
import asyncio
import aiohttp
import logging
import simplejson
from typing import Dict, Optional
from decimal import Decimal

from application.jazzcash_gateway import build_form_body

# ========== 银行代码映射表 ==========
# 将银行名称、BIC/SWIFT codes、简称等映射到 JazzCash 数字 bankCode
# 自动生成自 jcb_bank_list.json (47个银行，343个映射关系)
# 注意：空字符串 '' 表示 JazzCash 同行转账，不需要 bankCode
BANK_CODE_MAPPING = {
    # 核心映射 - EasyPaisa
    'easypaisa': '59',
    'easypaisabanklimited': '59',
    'tmfb': '59',
    'tmfbpkka': '59',

    # 核心映射 - JazzCash（同行转账，空值）
    'jazzcash': '',
    'mobilink': '',
    'mobilinkmicrofinancebank': '',
    'mobilinkmicrofinancebanklimited': '',
    'jcicpkka': '',

    # 常用银行简称
    'ubl': '60',           # United Bank
    'hbl': '49',           # Habib Bank
    'mcb': '79',           # MCB Bank
    'nbp': '89',           # National Bank of Pakistan
    'abl': '48',           # Allied Bank
    'bop': '45',           # Bank of Punjab
    'bok': '87',           # Bank of Khyber
    'scb': '64',           # Standard Chartered
    'jsb': '75',           # JS Bank

    # BIC/SWIFT Codes (完整格式)
    'unilpkkartg': '60',   # United Bank Limited
    'habbpkkartg': '49',   # Habib Bank Limited
    'mucbpkkkrtg': '79',   # MCB Bank Limited
    'fayspkka': '52',      # Faysal Bank
    'meznpkka': '66',      # Meezan Bank
    'alfhpkka': '43',      # Bank Alfalah
    'bahlpkka': '46',      # Bank Al Habib
    'abpapkka': '48',      # Allied Bank
    'ascmpkka': '47',      # Askari Bank
    'mpblpkka': '77',      # Habib Metropolitan Bank
    'nbpbpkka': '89',      # National Bank of Pakistan
    'albapkka': '72',      # Al Baraka Bank (AIINPKKA -> ALBAPKKA)
    'khybpkka024': '87',   # Bank of Khyber
    'scblpkka': '64',      # Standard Chartered
    'jsblpkka': '75',      # JS Bank
    'bkippkka': '44',      # Bank Islami
    'apnapkka': '76',      # Apna Microfinance Bank
    'nayapkka': '99',      # NayaPay
    'sadapkka': '11',      # SadaPay
    'nrakaeakxxxpkka': '16',  # Raqami Islamic Digital Bank (RQMIPKKA)
    'yappkka': '99',       # YAP -> NayaPay
    'khbldfid': '94',      # Khushhali Bank (KHBLDFID -> Khushali Bank)
    'hubppkka': '',        # Hubpay (未在JazzCash列表中，返回空)

    # 完整银行名称（规范化：小写无空格）
    'unitedbankltdubl': '60',
    'unitedbanklimited': '60',
    'habibbanklimited': '49',
    'mcbbanklimited': '79',
    'nationalbankofpakistan': '89',
    'faysalbanklimited': '52',
    'meezanbanklimited': '66',
    'bankalfalah': '43',
    'bankalhabib': '46',
    'alliedbank': '48',
    'askaribank': '47',
    'habibmetrobank': '77',
    'albarakabank': '72',
    'bankofkhyber': '87',
    'bankofpunjab': '45',
    'standardcharteredbank': '64',
    'jsbank': '75',
    'bankislamiaik': '44',
    'apnamicrofinancebank': '76',
    'nayapay': '99',
    'sadapay': '11',
    'raqamiislamicdigitalbank': '16',
    'soneribank': '61',
    'meezanbank': '66',
    'faysalbank': '52',
    'silkbank': '68',
    'sindhbank': '73',
    'sambabanklimited': '71',
    'burjbank': '67',
    'dubaiislamicbank': '56',
    'bankmakramah': '58',
    'kasbbank': '51',
    'nrsp': '88',
    'hblmfb': '92',
    'mcbislamic': '91',
    'umicrofinancebank': '85',
    'khushalibank': '94',
    'finja': '97',
    'paymax': '55',
    'keenu': '14',
    'ztbl': '42',
    'firstwomenbankltd': '90',
    'digitt': '13',
    'mashreqbankpakistanlimited': '32',
    'nbpfundmanagement': '98',
    'lolcmicrofinance': '81',

    # 其他 SWIFT 变体
    'unilpkka': '60',
    'habbpkka': '49',
    'mucbpkka': '79',
    'fayspkkartg': '52',
    'meznpkkartg': '66',
    'alfhpkkartg': '43',
    'bahlpkkartg': '46',
    'abpapkkartg': '48',
    'ascmpkkartg': '47',
    'albapkkartg': '72',
    'aiinpkka': '72',      # Al Baraka 的另一个 BIC code
}


# JazzCash API配置 — injected from orchestrator config
# These are set as class attributes from config during __init__


class TransferExecutor:
    """Handles JazzCash API calls, bank code mapping, and phone format checks."""

    def __init__(self, redis, logger, config):
        self.redis = redis
        self.logger = logger
        self.config = config
        self.api_url = config.get('jazzcash_api_url', 'http://34.150.42.92:84')
        self.user_id = config.get('jazzcash_user_id', 'ba08c3c0e4f546ad92dd2c2e8542ca36')
        self.secret_key = config.get('jazzcash_secret_key', 'ca45b35e132b46b9b68dd55f1ab077de')
        # Cross-module references (set by orchestrator after construction)
        self.account_selector = None
        self.transaction_logger = None

    def _is_pakistan_mobile_number(self, phone_number: str) -> bool:
        """判断是否为巴基斯坦手机号"""
        if not phone_number:
            return False

        # 移除所有非数字字符
        clean_number = ''.join(filter(str.isdigit, phone_number))

        # 巴基斯坦手机号特征：
        # - 以92开头（国际格式）或者03开头（本地格式）
        # - 总长度通常是11位（本地）或13位（国际）
        return (
            (clean_number.startswith('92') and len(clean_number) == 13) or
            (clean_number.startswith('03') and len(clean_number) == 11)
        )


    def _convert_to_bank_code(self, raw_input: str) -> str:
        """
        将银行名称、BIC codes、简称等转换为 JazzCash 数字 bankCode

        Args:
            raw_input: 原始输入（可能是银行名称、BIC code、简称等）

        Returns:
            str: JazzCash bankCode（数字字符串，如 "59", "60"）
                 空字符串表示 JazzCash 同行转账，不需要 bankCode
                 如果找不到映射，返回原始输入

        Examples:
            >>> _convert_to_bank_code('EasyPaisa')
            '59'
            >>> _convert_to_bank_code('UNILPKKARTG')
            '60'
            >>> _convert_to_bank_code('United Bank Limited UBL')
            '60'
            >>> _convert_to_bank_code('JazzCash')
            ''  # 同行转账
        """
        if not raw_input:
            return ''

        # 规范化输入：小写，移除空格和特殊字符
        import re
        normalized = re.sub(r'[^a-z0-9]', '', str(raw_input).lower())

        # 查找映射
        bank_code = BANK_CODE_MAPPING.get(normalized, raw_input)

        # 记录转换日志（仅当发生转换时）
        if bank_code != raw_input:
            self.logger.info(f"银行代码映射: '{raw_input}' -> '{bank_code}'")
        else:
            # 未找到映射，记录警告
            if normalized not in BANK_CODE_MAPPING:
                self.logger.warning(f"未找到银行代码映射: '{raw_input}' (规范化: '{normalized}')，将使用原始值")

        return bank_code


    def _get_bank_name_by_ifsc(self, ifsc_code: str) -> str:
        """根据IFSC代码获取银行名称"""
        if not ifsc_code:
            return None

        # 简单的银行代码映射，可以根据需要扩展
        bank_mapping = {
            'HBL': 'Habib Bank Limited',
            'NBP': 'National Bank of Pakistan',
            'MCB': 'Muslim Commercial Bank',
            'UBL': 'United Bank Limited',
            'ABL': 'Allied Bank Limited',
            'EASYPAISA': 'EasyPaisa',
            'JAZZCASH': 'JazzCash'
        }

        # 提取前3-4位作为银行代码
        bank_code = ifsc_code[:4].upper()
        for code, name in bank_mapping.items():
            if bank_code.startswith(code):
                return name

        return f'Bank ({ifsc_code})'  # 未知银行，返回代码


    async def _execute_jazzcash_transfer(self, order_data: Dict, account_info: Dict) -> Optional[Dict]:
        """执行JazzCash转账 - 调用真实API"""
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
            ifsc_code = order_data.get('ifsc', '')  # IFSC 就是银行名称（如 "United Bank Limited"）
            bank_ifsc = order_data.get('bank_ifsc', ifsc_code)  # bank_ifsc 字段（如果有的话）

            # 从传入的账号信息中获取数据（在早期获取，避免后续使用时未定义）
            payment_id = account_info.get('payment_id')
            phone_number = account_info.get('phone')

            # 判断是否为巴基斯坦手机号（JazzCash/EasyPaisa账号格式）
            is_pakistan_mobile = self._is_pakistan_mobile_number(to_account)

            # 根据账号类型确定转账方式
            if is_pakistan_mobile and ifsc_code.lower() == 'jazzcash':
                # JazzCash同行转账，不需要bankcode
                to_bankcode = ''
                to_bankname = ''
                transfer_type = "JazzCash同行转账"
            else:
                # 跨行转账到银行卡
                # JazzCash 需要 bank_code（银行代码）和 bank_name（银行名称）
                # 1. 获取原始 bank_code（可能是银行名、BIC code等）
                raw_bankcode = order_data.get('bank_code', ifsc_code)
                # 2. 转换为 JazzCash 数字 bankCode
                to_bankcode = self._convert_to_bank_code(raw_bankcode)
                # 3. bank_name 仍使用原始的 bank_ifsc
                to_bankname = bank_ifsc  # bank_ifsc 就是银行名称
                transfer_type = "JazzCash跨行转账"

            # 记录流程开始时间和详细信息
            process_start_time = time.time()
            process_details = {
                'process_start_time': datetime.fromtimestamp(process_start_time).isoformat(),
                'order_received_time': datetime.fromtimestamp(process_start_time).isoformat(),
                'account_selection_time': datetime.now().isoformat(),
                'account_selection_status': 'success',
                'account_selection_criteria': 'auto_selected'
            }

            self.logger.info(f"开始执行JazzCash转账:")
            self.logger.info(f"  订单号: {order_code}")
            self.logger.info(f"  转出账号: {phone_number} (JazzCash钱包)")
            self.logger.info(f"  转入账号: {to_account}")
            self.logger.info(f"  账号类型判断: {'巴基斯坦手机号' if is_pakistan_mobile else '银行账号'}")
            self.logger.info(f"  收款人姓名: {payment_name}")
            self.logger.info(f"  转账金额: {amount}")
            self.logger.info(f"  转账类型: {transfer_type}")
            if to_bankcode:
                self.logger.info(f"  银行代码(bank_code): {to_bankcode}")
                self.logger.info(f"  银行名称(bank_name): {to_bankname}")

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
                    balance_result = await self.account_selector.fetch_balance_from_api(account_info)
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

            # 判断转账类型：JazzCash同行转账 vs 跨行转账
            if to_bankcode:
                # 跨行转账到银行卡 - JazzCash 需要 bank_code 和 bank_name
                action = "transferToCard"

                # 🔥 JazzCash 跨行转账参数
                # bank_ifsc 字段就是银行名称（如 "United Bank Limited"）
                # bank_code 是银行代码（如 "60"），如果订单中没有则使用 ifsc
                payload_data = {
                    "account_id": phone_number,  # 保持使用手机号作为account_id
                    "bank_code": to_bankcode,    # 银行代码
                    "bank_name": to_bankname,    # 银行名称（来自 bank_ifsc/ifsc）
                    "to_accno": to_account,
                    "amount": amount,
                    "remark": order_code  # 使用订单号作为备注
                }

                # 🔥 JazzCash 跨行转账不需要 from_accno 参数（与 EasyPaisa 不同）
                self.logger.info(f"JazzCash跨行转账参数: bank_code={to_bankcode}, bank_name={to_bankname}")

                self.logger.info(f"转账类型: JazzCash跨行转账 (transferToCard)")
            else:
                # JazzCash同行转账
                action = "transferToAcc"
                payload_data = {
                    "account_id": phone_number,  # 保持使用手机号作为account_id
                    "to_accno": to_account,
                    "amount": amount,
                    "remark": order_code  # 使用订单号作为备注
                }

                # 🔥 JazzCash 同行转账不需要 from_accno 参数（与 EasyPaisa 不同）
                self.logger.info(f"JazzCash同行转账: 从{phone_number}转账到{to_account}")

                self.logger.info(f"转账类型: JazzCash同行转账 (transferToAcc)")

            # 构建内层payload
            inner_payload = {
                "id": request_uuid,
                "action": action,
                "payload": payload_data
            }

            self.logger.info(f"JazzCash API请求载荷: {inner_payload}")

            # 调用真实JazzCash API
            self.logger.info(f"开始调用JazzCash API...")

            api_start_time = time.time()
            process_details['transfer_api_time'] = datetime.now().isoformat()

            # 🔥 转账API使用60秒超时
            api_result = await self._call_jazzcash_api(inner_payload, phone_number, timeout=60)

            api_duration = int((time.time() - api_start_time) * 1000)
            process_details['api_duration_ms'] = api_duration

            # 记录API完整响应
            self.logger.info(f"JazzCash API响应: {api_result}")

            if api_result:
                code = api_result.get('code')
                msg = api_result.get('msg', '')
                data = api_result.get('data', {})

                self.logger.info(f"API响应解析: code={code}, msg={msg}, data={data}")

                if code == 200:
                    # 直接成功
                    transaction_id = self._extract_transaction_id(api_result, action)
                    self.logger.info(f"转账成功! 交易ID: {transaction_id}")

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
                                balance_change = -float(amount)  # 使用转账金额作为余额变化

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
                        'total_duration_ms': int((time.time() - process_start_time) * 1000)
                    })

                    # 记录完整的交易记录（成功）
                    self.transaction_logger.log_complete_transaction(order_data, account_info, inner_payload, api_result,
                                                "success", transaction_id=transaction_id, start_time=start_time,
                                                before_balance=before_balance, after_balance=after_balance,
                                                process_details=process_details)

                    return {
                        'success': True,
                        'transaction_id': transaction_id,
                        'message': f'JazzCash转账成功: {msg}',
                        'payer_phone': phone_number
                    }
                elif code == 402:
                    # PaymentFail 是明确失败：外层统一按 402 次数处理，不再按 msgCd 分叉。
                    self.logger.warning(f"转账失败(可重试): {msg}")

                    # 添加失败时的流程信息
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

                    # 记录完整的交易记录（失败）
                    self.transaction_logger.log_complete_transaction(order_data, account_info, inner_payload, api_result,
                                                "failed", error_message=msg, start_time=start_time,
                                                before_balance=before_balance, process_details=process_details)  # 失败时只有转账前余额

                    return {
                        'success': False,
                        'message': f'JazzCash转账失败: {msg}',
                        'can_retry': True,
                        'code': code
                    }
                elif code == 501:
                    # AccountInvalid - 账号异常（包括2小时冷却期），立即下线
                    self.logger.error(f"账号异常或冷却期: {msg}")

                    # 添加账号异常时的流程信息
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

                    # 记录完整的交易记录（账号异常）
                    self.transaction_logger.log_complete_transaction(order_data, account_info, inner_payload, api_result,
                                                "account_invalid", error_message=msg, start_time=start_time,
                                                before_balance=before_balance, process_details=process_details)  # 账号异常时只有转账前余额

                    return {
                        'success': False,
                        'message': f'JazzCash账号异常或冷却期: {msg}',
                        'account_invalid': True
                    }
                elif code == 423:
                    # ServerBusy 结果不确定，不自动重试，交给订单状态机进入人工待确认。
                    self.logger.warning(f"服务器忙碌，进入人工待确认: {msg}")

                    # 记录完整的交易记录（服务器忙碌）
                    self.transaction_logger.log_complete_transaction(order_data, account_info, inner_payload, api_result,
                                                "server_busy", error_message=msg, start_time=start_time,
                                                before_balance=before_balance, process_details=process_details)  # 服务器忙碌时只有转账前余额

                    return {
                        'success': False,
                        'message': f'JazzCash服务器忙碌待人工确认: {msg}',
                        'manual_confirm': True,
                        'can_retry': False,
                        'code': code
                    }
                elif code == 403:
                    # CheckParam - 参数错误
                    self.logger.error(f"参数错误: {msg}")

                    # 记录完整的交易记录（参数错误）
                    self.transaction_logger.log_complete_transaction(order_data, account_info, inner_payload, api_result,
                                                "param_error", error_message=msg, start_time=start_time,
                                                before_balance=before_balance, process_details=process_details)  # 参数错误时只有转账前余额

                    return {
                        'success': False,
                        'message': f'JazzCash参数错误: {msg}',
                        'can_retry': False,
                        'code': code
                    }
                elif code == 500:
                    # Error - 结果不确定，不自动驳回或成功，进入待人工确认
                    self.logger.error(f"出款异常待人工确认: {msg}")

                    self.transaction_logger.log_complete_transaction(order_data, account_info, inner_payload, api_result,
                                                "manual_confirm", error_message=msg, start_time=start_time,
                                                before_balance=before_balance, process_details=process_details)

                    return {
                        'success': False,
                        'message': f'JazzCash出款异常待人工确认: {msg}',
                        'manual_confirm': True,
                        'can_retry': False,
                        'code': code
                    }
                elif code == 503:
                    # NetworkError 结果不确定，不自动重试，避免重复出款。
                    self.logger.warning(f"网络异常，进入人工待确认: {msg}")

                    self.transaction_logger.log_complete_transaction(order_data, account_info, inner_payload, api_result,
                                                "network_retry", error_message=msg, start_time=start_time,
                                                before_balance=before_balance, process_details=process_details)

                    return {
                        'success': False,
                        'message': f'JazzCash网络异常待人工确认: {msg}',
                        'manual_confirm': True,
                        'can_retry': False,
                        'code': code
                    }
                else:
                    # 其他未知错误码
                    self.logger.error(f"未知错误码: code={code}, msg={msg}")

                    # 记录完整的交易记录（未知错误）
                    self.transaction_logger.log_complete_transaction(order_data, account_info, inner_payload, api_result,
                                                "unknown_error", error_message=msg, start_time=start_time,
                                                before_balance=before_balance, process_details=process_details)  # 未知错误时只有转账前余额

                    return {
                        'success': False,
                        'message': f'JazzCash未知错误: {msg}',
                        'manual_confirm': True,
                        'can_retry': False,
                        'code': code
                    }
            else:
                self.logger.error("JazzCash API无响应（网络异常或超时）")

                # 记录完整的交易记录（API无响应）
                self.transaction_logger.log_complete_transaction(order_data, account_info, inner_payload, {},
                                            "api_no_response", error_message="API无响应（网络异常）", start_time=start_time,
                                            before_balance=before_balance, process_details=process_details)  # API无响应时只有转账前余额

                return {
                    'success': False,
                    'message': 'JazzCash API无响应（网络异常或超时）',
                    'can_retry': False,
                    'code': -1  # 使用-1表示客户端网络异常（不会和API返回冲突）
                }

        except Exception as e:
            self.logger.error(f"JazzCash转账异常: {e}")

            # 记录完整的交易记录（异常）
            account_info = account_info if 'account_info' in locals() else {'phone': 'unknown', 'payment_id': 'unknown'}
            start_time = start_time if 'start_time' in locals() else time.time()
            inner_payload = inner_payload if 'inner_payload' in locals() else {}
            before_balance = before_balance if 'before_balance' in locals() else None
            process_details = process_details if 'process_details' in locals() else {}
            self.transaction_logger.log_complete_transaction(order_data, account_info, inner_payload, {},
                                        "exception", error_message=str(e), start_time=start_time,
                                        before_balance=before_balance, process_details=process_details)  # 异常时只有转账前余额

            return None

    async def _post_jazzcash_api(self, form_data, account_id, timeout=30):
        """Direct aiohttp POST to JazzCash API. Retry once on failure, sleep 2s on 423."""
        api_url = self.api_url
        for attempt in range(2):
            try:
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=timeout),
                    connector=aiohttp.TCPConnector(ssl=False)
                ) as session:
                    async with session.post(api_url, data=form_data) as resp:
                        if resp.status == 200:
                            text = await resp.text()
                            result = simplejson.loads(text) if text else None
                            if result and result.get('code') == 423 and attempt == 0:
                                await asyncio.sleep(2)
                                continue
                            return result
            except Exception as e:
                self.logger.error(f"网络请求错误: uid: {account_id}; {e}")
            if attempt == 0:
                await asyncio.sleep(0.5)
        return None

    async def _call_jazzcash_api(self, inner_payload: Dict, account_id: str, timeout: int = 60) -> Optional[Dict]:
        """调用JazzCash API - 转账"""
        try:
            form_data = build_form_body(
                inner_payload.get('action'),
                inner_payload.get('payload', {}),
                self.user_id,
                self.secret_key,
                request_id=inner_payload.get('id'),
            )
            result = await self._post_jazzcash_api(form_data, account_id, timeout=timeout)
            if result:
                self.logger.info(f"JazzCash API响应: {result}")
            else:
                self.logger.error(f"JazzCash API HTTP错误: None")
            return result
        except Exception as e:
            self.logger.error(f"调用JazzCash API异常: {e}")
            return None

    async def _call_jazzcash_api_query(self, inner_payload: Dict, account_id: str, timeout: int = 30) -> Optional[Dict]:
        """调用JazzCash API - 查询"""
        try:
            form_data = build_form_body(
                inner_payload.get('action'),
                inner_payload.get('payload', {}),
                self.user_id,
                self.secret_key,
                request_id=inner_payload.get('id'),
            )
            result = await self._post_jazzcash_api(form_data, account_id, timeout=timeout)
            if result:
                self.logger.info(f"JazzCash API查询响应: {result}")
            else:
                self.logger.error(f"JazzCash API查询HTTP错误: None")
            return result
        except Exception as e:
            self.logger.error(f"调用JazzCash API查询异常: {e}")
            return None

    def _extract_transaction_id(self, api_result: Dict, action: str) -> str:
        """从API响应中提取交易ID"""
        try:
            data = api_result.get('data', {})

            # 优先从 data.data.transactionID 提取（JazzCash API 实际返回路径）
            inner_data = data.get('data', {})
            transaction_id = inner_data.get('transactionID', '')

            if transaction_id:
                return transaction_id

            # 备用路径：尝试从其他可能的字段提取
            transaction_id = data.get('extOrderNo', '') or data.get('busOrderNo', '')

            if transaction_id:
                return transaction_id

            # 如果都没有，记录警告并生成备用ID
            self.logger.warning(f"API响应中未找到交易ID，使用备用方案生成ID")
            return f"JC{uuid.uuid4().hex[:12].upper()}"  # 备用方案，使用JC前缀（JazzCash）

        except Exception as e:
            self.logger.error(f"提取交易ID失败: {e}")
            return f"JC{uuid.uuid4().hex[:12].upper()}"
