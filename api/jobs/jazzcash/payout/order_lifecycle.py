"""
JazzCash Order Lifecycle — Order processing pipeline, risk checks.
Extracted from jazzcash_auto_payout.py Phase 3 refactoring.
"""
import os
import time
import json
import asyncio
import pymysql
import traceback
import logging
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime

from config import get_config
from application.websocket import callback

conf = get_config()


class OrderLifecycle:
    """Handles order processing pipeline and risk checks."""

    def __init__(self, redis, logger, config, settlement, transfer_executor, account_selector, transaction_logger):
        self.redis = redis
        self.logger = logger
        self.config = config
        self.settlement = settlement
        self.transfer_executor = transfer_executor
        self.account_selector = account_selector
        self.transaction_logger = transaction_logger
        self.REDIS_KEYS = config.get('redis_keys', {})
        self.lock_time = config.get('lock_time', 120)

    async def get_pending_orders_by_time(self) -> List[Dict]:
        """获取按时间排序的待处理订单 (保持现有业务逻辑)"""
        try:
            connection = pymysql.connect(
                host=conf['mysql_host'],
                user=conf['mysql_user'],
                password=conf['mysql_password'],
                database=conf['mysql_database'],
                charset='utf8mb4',
                autocommit=False
            )

            with connection.cursor() as cur:
                sql = """
                    SELECT code, amount, payment_id, payment_account, payment_name, remark, time_create, retry_count
                    FROM orders_df
                    WHERE status = 0
                      AND time_create >= DATE_SUB(NOW(), INTERVAL 3 DAY)
                    ORDER BY time_create ASC
                    LIMIT 100
                """

                cur.execute(sql)
                rows = cur.fetchall()

                orders = []
                for row in rows:
                    orders.append({
                        'code': row[0],
                        'amount': float(row[1]),
                        'payment_id': row[2],
                        'payment_account': row[3],
                        'payment_name': row[4],
                        'remark': row[5],
                        'time_create': row[6],
                        'retry_count': row[7]
                    })

                self.logger.info(f"从数据库获取到 {len(orders)} 个待处理订单")

                # 🔥 新增：批量过滤冷却期内的订单
                if orders:
                    filtered_orders = self.account_selector.filter_cooldown_orders(orders)
                    cooldown_count = len(orders) - len(filtered_orders)
                    if cooldown_count > 0:
                        self.logger.info(f"过滤掉 {cooldown_count} 个冷却期内的订单，剩余 {len(filtered_orders)} 个可处理")

                    # 新增：检查可用账号余额是否满足最小订单金额
                    if filtered_orders:
                        min_order_amount = min(order['amount'] for order in filtered_orders)
                        self.logger.info(f"当前待处理订单最小金额: {min_order_amount}")

                        # 从有序集合获取高余额账号（余额 >= 最小订单金额）
                        available_accounts = self.account_selector.get_top_balance_accounts(min_balance=min_order_amount, count=20)

                        if not available_accounts:
                            self.logger.warning(f"⚠️ 无余额满足要求的账号（最小金额:{min_order_amount}），跳过本轮处理")
                            return []

                        # 检查最大可用余额
                        max_available_balance = max(
                            account.get('balance', 0) for account in available_accounts
                        )

                        self.logger.info(f"可用账号最大余额: {max_available_balance}, 最小订单金额: {min_order_amount}")

                        if max_available_balance < min_order_amount:
                            self.logger.warning(
                                f"⚠️ 所有可用账号余额({max_available_balance})均小于最小订单金额({min_order_amount})，"
                                f"跳过本轮处理，待处理订单数: {len(filtered_orders)}"
                            )
                            return []

                        self.logger.info(f"✅ 存在可用账号余额满足要求，继续处理 {len(filtered_orders)} 个订单")

                    return filtered_orders
                else:
                    return orders

        except Exception as e:
            self.logger.error(f"获取待处理订单失败: {e}")
            return []
        finally:
            if 'connection' in locals():
                connection.close()

    async def prepare_account_and_locks(self, order_data: Dict) -> Dict:
        """
        为订单准备账号并获取必要的锁

        参数：
            order_data: 订单数据

        返回：
            {
                'success': True/False,
                'selected_account': {...},  # 成功时返回
                'order_lock_value': '...',  # 成功时返回
                'account_lock': '...',      # 成功时返回
                'payment_id_lock_value': '...',  # 成功时返回
                'account_id': '...',        # 成功时返回
                'payment_id': '...',        # 成功时返回
                'message': '...'
            }
        """
        order_code = order_data['code']
        amount = Decimal(str(order_data['amount']))
        target_account = order_data.get('payment_account', '')

        # 初始化变量，用于异常时的清理
        selected_account = None
        order_lock_value = None
        account_lock = None
        payment_id_lock_value = None
        account_id = None
        payment_id = None

        try:
            # 1. 获取可用账号
            self.logger.info(f"订单{order_code} 开始选择可用账号，金额: {amount}")
            accounts = await self.account_selector.get_available_accounts(amount, target_account)

            # ===================== 新增代付专卡专户过滤开始 =====================
            # 新增代付专卡专用
            # 如果订单有指定需要用的出款账户，则从accounts中只挑选指定的专户。如果不指定则从广泛匹配号列表移除全局专卡专户登记的银行卡
            target_payment_filtered_accounts = []
            if order_data['target_payment']:
                target_payment_filtered_accounts = [account for account in accounts if account['payment_id'] in order_data['target_payment'].split(',')]
            else:
                target_payment_key: str = (self.redis.get("target_payment_key") or b"").decode()
                target_payment_filtered_accounts = [account for account in accounts if account['payment_id'] not in target_payment_key.split(',')]
            accounts = target_payment_filtered_accounts
            # ===================== 新增代付专卡专户过滤结束 =====================

            if not accounts:
                return {
                    'success': False,
                    'message': f'订单{order_code} 暂无可用账号'
                }

            # 2. 选择最优账号
            selected_account = accounts[0]
            account_id = selected_account['phone']
            payment_id = selected_account['payment_id']

            self.logger.info(
                f"订单{order_code} 选择账号: {account_id}, "
                f"payment_id: {payment_id}, 余额: {selected_account.get('balance', 'N/A')}"
            )

            # 🔥 3. 获取订单锁（有可用账号后才获取）
            order_lock_value = self.account_selector.get_lock(order_code)
            if not order_lock_value:
                self.account_selector.return_account_to_active_list(selected_account)
                return {
                    'success': False,
                    'message': f'订单{order_code} 未抢到订单锁'
                }

            self.logger.info(f"订单{order_code} 成功获取订单锁")

            # 4. 获取账号锁
            account_lock = await self.account_selector.acquire_account_lock(account_id, order_code)
            if not account_lock:
                # 账号锁失败，释放订单锁
                self.account_selector.del_lock(order_code, order_lock_value)
                self.account_selector.return_account_to_active_list(selected_account)
                return {
                    'success': False,
                    'message': f'订单{order_code} 账号{account_id}被锁定'
                }

            self.logger.info(f"订单{order_code} 成功获取账号锁: {account_id}")

            # 5. 获取 payment_id 锁
            payment_id_lock_value = self.account_selector.get_payment_id_lock(payment_id)
            if not payment_id_lock_value:
                # payment_id 锁定失败，释放订单锁和账号锁
                self.account_selector.release_account_lock(account_id, account_lock)
                self.account_selector.del_lock(order_code, order_lock_value)
                self.account_selector.return_account_to_active_list(selected_account)
                return {
                    'success': False,
                    'message': f'订单{order_code} Payment ID {payment_id} 锁定失败'
                }

            self.logger.info(f"订单{order_code} 成功获取 payment_id 锁: {payment_id}")

            # 6. 成功返回
            return {
                'success': True,
                'selected_account': selected_account,
                'order_lock_value': order_lock_value,
                'account_lock': account_lock,
                'payment_id_lock_value': payment_id_lock_value,
                'account_id': account_id,
                'payment_id': payment_id
            }

        except Exception as e:
            self.logger.error(f"订单{order_code} 准备账号和锁异常: {e}")

            # 清理已获取的锁
            if payment_id_lock_value and payment_id:
                try:
                    self.account_selector.del_payment_id_lock(payment_id, payment_id_lock_value)
                except:
                    pass

            if account_lock and account_id:
                try:
                    self.account_selector.release_account_lock(account_id, account_lock)
                except:
                    pass

            if order_lock_value:
                try:
                    self.account_selector.del_lock(order_code, order_lock_value)
                    self.logger.info(f"订单{order_code} 异常时释放订单锁")
                except Exception as lock_e:
                    self.logger.error(f"释放订单锁失败: {lock_e}")

            if selected_account:
                try:
                    self.account_selector.return_account_to_active_list(selected_account)
                except:
                    pass

            return {
                'success': False,
                'message': f'订单{order_code} 准备失败: {str(e)}'
            }

    # ========== 风控控制器 ==========

    async def check_payout_risk(self, order_data: Dict) -> Dict:
        """风控检查"""
        try:
            # 检查紧急停机（使用 EasyPaisa 的配置，全局控制）
            emergency_stop = self.redis.get('easypaisa_emergency_stop')
            if emergency_stop == b"1" or emergency_stop == "1":
                return {'passed': False, 'reason': 'emergency_stop', 'message': '系统紧急停机'}

            amount = Decimal(str(order_data['amount']))

            # 基础金额检查
            if amount < Decimal('0.1'):    # 单笔少于0.1
                return {'passed': False, 'reason': 'amount_too_small', 'message': '单笔金额过小'}

            # 检查系统负载
            active_orders_key = 'jazzcash_active_orders_count'
            active_count = self.redis.get(active_orders_key)
            if active_count and int(active_count.decode()) > 100:  # 超过100个活跃订单
                return {'passed': False, 'reason': 'system_overload', 'message': '系统负载过高'}

            return {'passed': True}

        except Exception as e:
            self.logger.error(f"风控检查异常: {e}")
            return {'passed': True, 'message': '风控检查异常，放行处理'}

    # ========== 调度引擎 ==========

    async def process_payout_order(self, order_data: Dict, connection=None, selected_account: Dict = None) -> Dict:
        """代付订单处理"""
        order_code = order_data['code']
        amount = Decimal(str(order_data['amount']))

        self.logger.info(f"开始处理代付订单: {order_code}, 金额: {amount}")

        # 🔥 使用外部传入的账号
        account_id = selected_account['phone']
        payment_id = selected_account['payment_id']

        try:
            # 1. 风控检查
            risk_result = await self.check_payout_risk(order_data)
            if not risk_result['passed']:
                # 记录操作日志（风控拦截）
                try:
                    self.transaction_logger.log_complete_transaction(
                        order_data,
                        {'phone': 'risk_blocked', 'payment_id': None},
                        {},
                        {},
                        "risk_blocked",
                        error_message=f"风控拦截: {risk_result.get('message', risk_result['reason'])}",
                        start_time=time.time(),
                        before_balance=None,
                        process_details={'risk_check_result': risk_result, 'block_stage': 'risk_check'}
                    )
                except Exception as log_e:
                    self.logger.warning(f"记录风控拦截日志失败: {log_e}")

                return {
                    'success': False,
                    'message': f"风控拦截: {risk_result.get('message', risk_result['reason'])}"
                }

            # 🔥 以下代码已移到 process_single_order_async 中执行
            # # 2. 获取可用账号 (传入收款账号用于过滤)
            # target_account = order_data.get('payment_account', '')
            # accounts = await self.account_selector.get_available_accounts(amount, target_account)
            # if not accounts:
            #     # 没有可用账号时，等待下次轮询处理
            #     self.logger.info(f"订单 {order_code} 暂无可用账号，等待下次轮询")
            #
            #     # 记录操作日志（无可用账号）
            #     try:
            #         self.transaction_logger.log_complete_transaction(
            #             order_data,
            #             {'phone': 'no_account_available', 'payment_id': None},
            #             {},
            #             {},
            #             "no_available_account",
            #             error_message="暂无可用账号，等待下次轮询",
            #             start_time=time.time(),
            #             before_balance=None,
            #             process_details={'block_stage': 'account_selection', 'required_amount': float(amount)}
            #         )
            #     except Exception as log_e:
            #         self.logger.warning(f"记录无可用账号日志失败: {log_e}")
            #
            #     return {
            #         'success': False,
            #         'message': '暂无可用账号，等待下次轮询',
            #         'retry': True
            #     }
            #
            # # 3. 选择最优账号
            # selected_account = accounts[0]
            # account_id = selected_account['phone']  # 🔥 修复: 使用phone作为EasyPaisa的account_id
            #
            # # 4. 获取账号锁
            # # account_lock = await self.account_selector.acquire_account_lock(account_id, order_code)
            # if not account_lock:
            #     # 账号被锁定，将账号重新入队
            #     self.account_selector.return_account_to_active_list(selected_account)  # 🔥 修复: 传入完整账号信息
            #
            #     # 记录操作日志（账号锁定失败）
            #     try:
            #         self.transaction_logger.log_complete_transaction(
            #             order_data,
            #             selected_account,
            #             {},
            #             {},
            #             "account_lock_failed",
            #             error_message=f"账号{account_id}被锁定，已重新排队",
            #             start_time=time.time(),
            #             before_balance=None,
            #             process_details={'block_stage': 'account_lock', 'account_id': account_id, 'payment_id': selected_account.get('payment_id')}
            #         )
            #     except Exception as log_e:
            #         self.logger.warning(f"记录账号锁定失败日志失败: {log_e}")
            #
            #     return {
            #         'success': False,
            #         'message': f'账号{account_id}被锁定，已重新排队',
            #         'payment_id': selected_account.get('payment_id'),
            #         'partner_id': selected_account.get('partner_id')
            #     }
            #
            # # 5. 获取payment_id锁（在账号锁之后）
            # # payment_id = selected_account['payment_id']
            # payment_id_lock_value = None  # 在外部定义，确保finally块可以访问
            # payment_id_lock_value = self.account_selector.get_payment_id_lock(payment_id)
            # if not payment_id_lock_value:
            #     # payment_id锁定失败，释放账号锁并重新入队
            #     self.account_selector.release_account_lock(account_id, account_lock)
            #     self.account_selector.return_account_to_active_list(selected_account)
            #
            #     # 记录操作日志（Payment ID锁定失败）
            #     try:
            #         self.transaction_logger.log_complete_transaction(
            #             order_data,
            #             selected_account,
            #             {},
            #             {},
            #             "payment_id_lock_failed",
            #             error_message=f"Payment ID {payment_id} 锁定失败，已重新排队",
            #             start_time=time.time(),
            #             before_balance=None,
            #             process_details={'block_stage': 'payment_id_lock', 'account_id': account_id, 'payment_id': payment_id}
            #         )
            #     except Exception as log_e:
            #         self.logger.warning(f"记录Payment ID锁定失败日志失败: {log_e}")
            #
            #     return {
            #         'success': False,
            #         'message': f'Payment ID {payment_id} 锁定失败，已重新排队',
            #         'payment_id': payment_id,  # 返回payment_id用于失败记录
            #         'partner_id': selected_account.get('partner_id')  # 返回partner_id用于失败记录
            #     }

            try:
                # 6. 执行JazzCash转账
                transfer_result = await self.transfer_executor._execute_jazzcash_transfer(order_data, selected_account)

                if transfer_result and transfer_result['success']:
                    # 🔥 转账成功，记录账号使用时间（动态冷却期）
                    self.account_selector.record_account_usage(selected_account['payment_id'])

                    # 转账成功后立即扣减Redis余额
                    self.settlement.update_account_balance_after_transfer(
                        payment_id=selected_account['payment_id'],
                        transfer_amount=amount
                    )

                    # 转账成功，设置账号释放时间（从配置读取）
                    self.account_selector.set_account_release_time(selected_account['payment_id'])
                    self.account_selector.return_account_to_active_list(selected_account)  # 🔥 修复: 传入完整账号信息

                    return {
                        'success': True,
                        'message': '转账成功',
                        'transaction_id': transfer_result.get('transaction_id'),
                        'account_used': account_id,
                        'payment_id': selected_account['payment_id'],
                        'partner_id': selected_account.get('partner_id'),  # 新增：返回partner_id供外部使用
                        'payer_phone': transfer_result.get('payer_phone'),
                        'selected_account': selected_account  # 新增：返回完整账户信息供外部使用
                    }
                elif transfer_result is None:
                    # Python异常（如连接异常、JSON解析错误等）按成功处理
                    self.account_selector.set_account_release_time(selected_account['payment_id'])  # 从配置读取释放时间
                    self.account_selector.return_account_to_active_list(selected_account)  # 🔥 修复: 传入完整账号信息

                    return {
                        'success': False,  # 🔥 修复: 不是真正成功
                        'treat_as_success': False,
                        'message': 'Python异常，按成功处理避免重复代付',
                        'account_used': account_id,
                        'payment_id': selected_account['payment_id'],
                        'partner_id': selected_account.get('partner_id')
                    }
                else:
                    # 转账失败，根据错误码区分处理
                    message = transfer_result.get('message', '')
                    error_code = transfer_result.get('code')
                    is_reject = transfer_result.get('reject', False)

                    # 放回账号到活跃列表（包括驳回情况）
                    self.account_selector.set_account_release_time(selected_account['payment_id'])  # 从配置读取释放时间
                    self.account_selector.return_account_to_active_list(selected_account)  # 🔥 修复: 传入完整账号信息

                    # 🔥 驳回情况：直接返回，由外层处理
                    if is_reject:
                        return transfer_result  # 直接返回驳回结果，包含 reject=True

                    # ✅ code=402 (转账失败) 特殊处理：放回订单池重试
                    if error_code in [402, 423, 503]:
                        return {
                            'success': False,
                            'treat_as_success': True,  # 放回订单池
                            'message': f"JazzCash转账失败/忙/网络异常，放回订单池重试: {message}",
                            'account_used': account_id,
                            'payment_id': selected_account['payment_id'],
                            'partner_id': selected_account.get('partner_id')
                        }
                    else:
                        # 其他错误码按失败处理，status=2（待确认），不放回订单池
                        return {
                            'success': False,
                            'treat_as_success': False,
                            'message': f"API失败(code={error_code})，按失败处理: {message}",
                            'account_used': account_id,
                            'payment_id': selected_account['payment_id'],
                            'partner_id': selected_account.get('partner_id')
                        }

            finally:
                # 注意：锁的释放统一在外层 process_single_order_async 的 finally 块中处理
                # 这里不需要释放锁，避免引用外层作用域的变量
                pass

        except asyncio.TimeoutError:
            # 会议决策：超时当成功处理
            self.logger.warning(f"订单{order_code}API超时，按成功处理")

            # 记录操作日志（早期异常 - 超时）
            try:
                # 如果selected_account未定义，使用默认值
                account_info = locals().get('selected_account', {'phone': 'unknown', 'payment_id': None})
                self.transaction_logger.log_complete_transaction(
                    order_data,
                    account_info,
                    {},
                    {},
                    "early_exception_timeout",
                    error_message="订单处理超时，按成功处理避免重复代付",
                    start_time=time.time(),
                    before_balance=None,
                    process_details={'exception_type': 'asyncio.TimeoutError', 'exception_stage': 'process_payout_order'}
                )
            except Exception as log_e:
                self.logger.warning(f"记录超时异常日志失败: {log_e}")

            # 获取selected_account信息（如果存在）
            if 'selected_account' in locals():
                return {
                    'success': False,
                    'treat_as_success': False,  # 超时不确定是否成功，设为待确认状态
                    'message': 'API超时，设为待确认状态待人工核实',
                    'payment_id': selected_account['payment_id'],
                    'partner_id': selected_account.get('partner_id')
                }
            else:
                # selected_account未定义说明异常发生在账号选择之前，没有payment_id
                return {
                    'success': False,
                    'treat_as_success': False,  # 超时不确定是否成功，设为待确认状态
                    'message': 'API超时，设为待确认状态待人工核实'
                }
        except Exception as e:
            # 会议决策：异常当成功处理
            self.logger.error(f"订单{order_code}处理异常: {e}")

            # 记录操作日志（早期异常 - 通用异常）
            try:
                # 如果selected_account未定义，使用默认值
                account_info = locals().get('selected_account', {'phone': 'unknown', 'payment_id': None})
                self.transaction_logger.log_complete_transaction(
                    order_data,
                    account_info,
                    {},
                    {},
                    "early_exception",
                    error_message=f"订单处理异常，按成功处理避免重复代付: {str(e)}",
                    start_time=time.time(),
                    before_balance=None,
                    process_details={'exception_type': type(e).__name__, 'exception_stage': 'process_payout_order', 'exception_detail': str(e)}
                )
            except Exception as log_e:
                self.logger.warning(f"记录处理异常日志失败: {log_e}")

            # 获取selected_account信息（如果存在）
            if 'selected_account' in locals():
                return {
                    'success': False,
                    'treat_as_success': True,
                    'message': f'处理异常，按成功处理避免重复代付: {str(e)}',
                    'payment_id': selected_account['payment_id'],
                    'partner_id': selected_account.get('partner_id')
                }
            else:
                # selected_account未定义说明异常发生在账号选择之前，没有payment_id
                return {
                    'success': False,
                    'treat_as_success': True,
                    'message': f'处理异常，按成功处理避免重复代付: {str(e)}'
                }

    async def process_single_order_async(self, order_message: str) -> bool:
        """异步处理单个订单 - 完整事务控制版本"""
        order_code = None
        order_lock_value = None
        connection = None
        payment_id = None  # 用于错误处理和失败记录
        payment_id_lock_value = None  # payment_id锁
        account_lock = None  # 账号锁
        account_id = None  # 账号ID
        success_result = False  # 初始化最终结果

        try:
            self.logger.info(f'收到订单消息: {order_message}')

            # 解析订单消息（格式：{code}_{amount}）
            parts = order_message.split('_')
            if len(parts) < 2:
                self.logger.error(f"订单消息格式错误: {order_message}")
                return False

            order_code = parts[0]
            amount = parts[1]

            # 🚨 处理前再次检查紧急停机状态（使用 EasyPaisa 的配置，全局控制）
            emergency_stop = self.redis.get("easypaisa_emergency_stop")
            if emergency_stop == b"1" or emergency_stop == "1":
                self.logger.warning(f"⚠️ 订单{order_code}处理前检测到全局紧急停机状态，停止处理")
                return False

            # 🔥 订单锁已移到 prepare_account_and_locks 中获取（有可用账号后才获取）

            # 1. 建立数据库连接和事务
            connection = pymysql.connect(
                host=conf['mysql_host'],
                user=conf['mysql_user'],
                password=conf['mysql_password'],
                db=conf['mysql_database'],
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=False  # 关闭自动提交，手动控制事务
            )

            try:
                with connection.cursor() as cur:
                    # 2. 查询订单信息（在事务内）
                    sql = 'SELECT * FROM orders_df WHERE code = %s'
                    cur.execute(sql, order_code)
                    order_data = cur.fetchone()

                    if not order_data:
                        self.logger.error(f'订单{order_code}不存在')
                        return False

                    # 检查订单状态
                    if order_data['status'] != 0:
                        self.logger.info(f'订单{order_code}已被处理，状态: {order_data["status"]}')
                        return False

                    # 注意：冷却期检查已在get_pending_orders_by_time中完成

                    # 🔥 3. 准备账号并获取锁（包含：选账号→订单锁→账号锁→payment_id锁）
                    prepare_result = await self.prepare_account_and_locks(order_data)

                    if not prepare_result['success']:
                        # ✅ 无可用账号或锁获取失败：不更新订单状态，直接返回
                        self.logger.info(
                            f"订单{order_code} 准备账号失败: {prepare_result['message']}，"
                            f"不更新订单状态，等待下次轮询"
                        )
                        return False

                    # 提取准备好的资源
                    selected_account = prepare_result['selected_account']
                    order_lock_value = prepare_result['order_lock_value']
                    account_lock = prepare_result['account_lock']
                    payment_id_lock_value = prepare_result['payment_id_lock_value']
                    account_id = prepare_result['account_id']
                    payment_id = prepare_result['payment_id']

                    self.logger.info(
                        f"订单{order_code} 准备完成: 账号{account_id}, payment_id={payment_id}"
                    )

                    # 🔥 4. 更新订单状态为处理中（确认有可用账号且已锁定后才更新）
                    sql = """
                        UPDATE orders_df
                        SET status = 1, time_accept = NOW()
                        WHERE code = %s AND status = 0
                    """
                    cur.execute(sql, (order_code,))
                    affected_rows = cur.rowcount
                    if affected_rows == 0:
                        self.logger.warning(f'订单{order_code}状态已不是0，可能已被其他进程处理，跳过')
                        return False
                    connection.commit()  # 立即提交，防止其他进程重复查询此订单
                    self.logger.info(f'订单{order_code}状态已更新为处理中(status=1)，事务已提交')

                    # 🔥 5. 执行转账（传入已选择的账号）
                    result = await self.process_payout_order(
                        order_data,
                        connection,
                        selected_account=selected_account
                    )

                    # 6. 记录处理该订单的 payment_id 和 partner_id（所有情况都记录）
                    # 🔥 payment_id 和 account_id 已经从 prepare_result 中提取（第5214行），用于finally释放锁
                    partner_id = selected_account.get('partner_id')

                    # 更新订单的 payment_id 和 partner_id
                    if partner_id:
                        # 同时设置payment_id和partner_id
                        sql = """
                            UPDATE orders_df
                            SET payment_id = %s, partner_id = %s
                            WHERE code = %s
                        """
                        cur.execute(sql, (payment_id, partner_id, order_code))
                        self.logger.info(f"订单{order_code}已分配账号 payment_id: {payment_id}, partner_id: {partner_id}")
                    else:
                        # 如果partner_id为空，只设置payment_id
                        sql = """
                            UPDATE orders_df
                            SET payment_id = %s
                            WHERE code = %s
                        """
                        cur.execute(sql, (payment_id, order_code))
                        self.logger.info(f"订单{order_code}已分配账号 payment_id: {payment_id} (partner_id为空)")

                    # 7. 如果处理成功，立即更新订单状态为3
                    if result.get('success', False):
                        self.logger.info(f"订单{order_code}转账成功，payment_id: {payment_id}")
                        # 🔥 优化：转账成功后立即更新订单状态为3
                        time_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        transaction_id = result.get('transaction_id', '')
                        sql_update_status = """
                            UPDATE orders_df
                            SET status = 3, time_payed = %s, time_success = %s, utr = %s
                            WHERE code = %s AND status IN (0, 1)
                        """
                        cur.execute(sql_update_status, (time_now, time_now, transaction_id, order_code))
                        affected_rows = cur.rowcount
                        if affected_rows > 0:
                            self.logger.info(f"✅ 订单{order_code}转账成功，状态已更新为成功(status=3)，transaction_id: {transaction_id}")
                        else:
                            self.logger.warning(f"⚠️ 订单{order_code}转账成功，但状态已不是0或1，可能已被其他进程处理")

                    # 8. 提交 payment_id 和订单状态更新事务
                    connection.commit()
                    self.logger.info(f'订单{order_code}payment_id已更新: {payment_id}, 订单状态: {result.get("success") and "成功" or "失败"}')

                    # 9. 根据处理结果分别处理（独立事务）
                    if result.get('success', False):
                        # 9.1 代付成功：处理余额、佣金、流水
                        success_connection = None
                        try:
                            self.logger.info(f"订单{order_code}开始处理余额、佣金和流水")

                            # 重新建立连接进行后续处理
                            success_connection = pymysql.connect(
                                host=conf['mysql_host'],
                                user=conf['mysql_user'],
                                password=conf['mysql_password'],
                                db=conf['mysql_database'],
                                charset='utf8mb4',
                                cursorclass=pymysql.cursors.DictCursor,
                                autocommit=False
                            )

                            try:
                                with success_connection.cursor() as success_cur:
                                    # 设置 qr_id 用于后续处理
                                    self.settlement.qr_id = result.get('payment_id')

                                    # 🔥 重新查询最新的订单数据（包含已更新的payment_id、partner_id、status等）
                                    sql_refresh = 'SELECT * FROM orders_df WHERE code = %s'
                                    success_cur.execute(sql_refresh, (order_code,))
                                    updated_order_data = success_cur.fetchone()

                                    if not updated_order_data:
                                        self.logger.error(f"重新查询订单{order_code}失败，数据不存在")
                                        success_result = False
                                    else:
                                        self.logger.info(f"✅ 重新查询订单{order_code}成功：status={updated_order_data.get('status')}, payment_id={updated_order_data.get('payment_id')}, partner_id={updated_order_data.get('partner_id')}")

                                        # 调用自己的success处理逻辑（使用最新的订单数据）
                                        if self.settlement.handle_payout_success(success_connection, success_cur, updated_order_data, result):
                                            success_connection.commit()
                                            self.logger.info(f"订单{order_code}success处理成功")
                                            success_result = True
                                        else:
                                            success_connection.rollback()
                                            self.logger.error(f"订单{order_code}success处理失败")
                                            success_result = False
                            finally:
                                if success_connection:
                                    success_connection.close()

                        except Exception as e:
                            self.logger.error(f"订单{order_code}调用success处理异常: {e}")
                            self.logger.error(traceback.format_exc())
                            success_result = False

                    elif result.get('reject', False):
                        # 9.2 驳回处理：退款 + status=-1（独立连接）
                        self.logger.warning(f'订单{order_code}需要驳回，开始执行驳回操作: {result.get("reject_reason")}')

                        reject_connection = None
                        try:
                            # 重新建立独立连接进行驳回处理
                            reject_connection = pymysql.connect(
                                host=conf['mysql_host'],
                                user=conf['mysql_user'],
                                password=conf['mysql_password'],
                                db=conf['mysql_database'],
                                charset='utf8mb4',
                                cursorclass=pymysql.cursors.DictCursor,
                                autocommit=False
                            )

                            # 调用驳回函数（使用独立连接）
                            reject_result = self.settlement.reject_order_with_refund(
                                order_data=order_data,
                                connection=reject_connection,
                                reason=result.get('reject_reason', 'Unknown rejection reason'),
                                selected_account=selected_account
                            )

                            if reject_result.get('reject', False):
                                # 驳回成功，提交
                                reject_connection.commit()
                                self.logger.info(f'✅ 订单{order_code}驳回成功，payment_id={payment_id}, status=-1，账号已放回活跃列表')

                                # 🔥 新增：发送驳回通知到Redis
                                try:
                                    self.redis.publish('order_df_notify', order_code)
                                    self.logger.info(f'📢 已发送驳回通知到Redis: {order_code}')
                                except Exception as e:
                                    self.logger.error(f'发送驳回通知失败: {order_code}, 错误: {e}')
                            else:
                                # 驳回失败
                                reject_connection.rollback()
                                self.logger.error(f'❌ 订单{order_code}驳回失败: {reject_result.get("message")}，但payment_id已记录')
                        except Exception as e:
                            self.logger.error(f'订单{order_code}驳回异常: {e}')
                            if reject_connection:
                                try:
                                    reject_connection.rollback()
                                except:
                                    pass
                        finally:
                            if reject_connection:
                                try:
                                    reject_connection.close()
                                except:
                                    pass

                        return False

                    else:
                        # 9.3 普通失败：处理重试逻辑
                        success_result = False

                        # 失败：检查是否为紧急停机
                        if 'emergency_stop' in result.get('message', '') or 'system紧急停机' in result.get('message', ''):
                            # 紧急停机：将订单重置为待处理状态（status=1已在第4471行提交，无法回滚）
                            self.logger.warning(f'⚠️ 订单{order_code}遇到紧急停机，重置为待处理状态: {result["message"]}')
                            sql = """
                                UPDATE orders_df
                                SET status = 0, time_accept = NULL
                                WHERE code = %s AND status = 1
                            """
                            cur.execute(sql, (order_code,))
                            connection.commit()
                            self.logger.info(f'订单{order_code}已重置为待处理状态(status=0)')
                            success_result = False
                            return success_result
                        elif result.get('treat_as_success', True):  # 默认按成功处理
                            # 先增加重试次数
                            current_retry_count = order_data.get('retry_count', 0)
                            new_retry_count = current_retry_count + 1

                            # 🔥 注释掉强制3次限制，改为完全按照冷却期配置处理
                            # if new_retry_count > 3:
                            #     # 重试次数超过3次，设置为异常按成功处理
                            #     sql = """
                            #         UPDATE orders_df
                            #         SET status = 5, time_payed = NOW(), time_success = NOW(), retry_count = %s
                            #         WHERE code = %s
                            #     """
                            #     cur.execute(sql, (new_retry_count, order_code,))
                            #     connection.commit()
                            #     self.logger.info(f'订单{order_code}重试次数超过3次，异常按成功处理(status=5)，重试次数: {current_retry_count} -> {new_retry_count}')
                            #
                            #     # 修改：重试次数超限按成功处理
                            #     # 但记录到订单冷却期Hash用于统计分析
                            #     updated_order_data = order_data.copy()
                            #     updated_order_data['retry_count'] = new_retry_count
                            #
                            #     # 设置订单冷却期（包括没有可用账号的情况）
                            #     self.account_selector.set_order_cooldown(
                            #         order_code,
                            #         result.get('payment_id'),  # 可能为None，方法内部会处理
                            #         result.get('message', '重试次数超过3次'),
                            #         updated_order_data,
                            #         status=3,  # 3: 超限异常按成功处理
                            #         available_payment_ids=result.get('available_payment_ids', [])  # 传入匹配的payment_id列表
                            #     )
                            #     self.logger.info(f'订单{order_code}重试超限，记录到统计分析，不影响payment_id')
                            #
                            #     success_result = True  # 异常按成功处理
                            # else:

                            # 🔥 新增：检查重试次数是否超过8次
                            if new_retry_count > 8:
                                # 超过8次，设置为失败状态
                                sql = """
                                    UPDATE orders_df
                                    SET status = 2, retry_count = %s
                                    WHERE code = %s AND status IN (0, 1)
                                """
                                cur.execute(sql, (new_retry_count, order_code,))
                                affected_rows = cur.rowcount
                                connection.commit()

                                if affected_rows > 0:
                                    self.logger.error(
                                        f'订单{order_code}重试次数超过8次，设置为失败状态(status=2)，'
                                        f'重试次数: {current_retry_count} -> {new_retry_count}'
                                    )
                                else:
                                    self.logger.warning(f'订单{order_code}状态已不是0或1，可能已被其他进程处理为成功(status=3)，跳过更新')

                                # 记录失败详情
                                if payment_id:
                                    self.account_selector.record_payment_failure(
                                        payment_id=payment_id,
                                        amount=order_data['amount'],
                                        to_account=order_data.get('payment_account', ''),
                                        reason=f"重试次数超过8次: {result.get('message', '')}",
                                        order_code=order_code
                                    )

                                success_result = False
                                return success_result

                            else:
                                # 未超过8次，继续重试
                                # 所有失败按成功处理的订单，更新重试次数并重新设为待处理状态，同时清除payment_id和partner_id
                                sql = """
                                    UPDATE orders_df
                                    SET retry_count = %s, status = 0, time_accept = NULL, payment_id = NULL, partner_id = NULL
                                    WHERE code = %s AND status IN (0, 1)
                                """
                                cur.execute(sql, (new_retry_count, order_code,))
                                affected_rows = cur.rowcount
                                connection.commit()  # 提交更新
                                if affected_rows > 0:
                                    self.logger.info(f'订单{order_code}按成功处理但继续重试，重新设为待处理状态（已清除payment_id和partner_id），重试次数: {current_retry_count} -> {new_retry_count}')
                                else:
                                    self.logger.warning(f'订单{order_code}状态已不是0或1，可能已被其他进程处理为成功(status=3)，跳过更新')

                                # 新增：所有按成功处理的失败都设置订单冷却期
                                failure_message = result.get('message', '')
                                # 更新订单数据的retry_count用于冷却期计算
                                updated_order_data = order_data.copy()
                                updated_order_data['retry_count'] = new_retry_count

                                self.account_selector.set_order_cooldown(
                                    order_code,
                                    result.get('payment_id'),  # 可能为None，方法内部会处理
                                    failure_message,
                                    updated_order_data,
                                    status=1
                                )
                                self.logger.info(f'订单{order_code}按成功处理的失败，已设置冷却期: {failure_message}')

                                success_result = False
                                return success_result  # 返回False
                        else:
                            # 真正的失败
                            current_retry_count = order_data.get('retry_count', 0)
                            new_retry_count = current_retry_count + 1
                            sql = """
                                UPDATE orders_df
                                SET status = 2, retry_count = %s
                                WHERE code = %s AND status IN (0, 1)
                            """
                            cur.execute(sql, (new_retry_count, order_code,))
                            affected_rows = cur.rowcount
                            connection.commit()
                            if affected_rows > 0:
                                self.logger.error(f'订单{order_code}处理失败，事务已提交: {result["message"]}')
                            else:
                                self.logger.warning(f'订单{order_code}状态已不是0或1，可能已被其他进程处理为成功(status=3)，跳过更新')

                            # 设置payment_id失败冷却期（只有当有payment_id时才设置）
                            if payment_id:
                                self.settlement.set_payment_id_failed(
                                    payment_id,
                                    result.get('message', '处理失败'),
                                    order_data,
                                    status=1  # 1: 真正失败
                                )

                                # 🔥 记录失败详情到统一Hash（用于重复订单检测）
                                self.account_selector.record_payment_failure(
                                    payment_id=payment_id,
                                    amount=order_data['amount'],
                                    to_account=order_data.get('payment_account', ''),
                                    reason=result.get('message', '处理失败'),
                                    order_code=order_code
                                )
                            else:
                                self.logger.info(f'订单{order_code}真正失败但无payment_id（如无可用账号），跳过payment_id冷却期设置')

                            # 注意：真正失败的订单不放入订单冷却期Hash，因为不会再重试

                            success_result = False

                    return success_result

            except Exception as e:
                # 任何异常都需要重置订单状态（status=1已在第4471行提交，无法回滚）
                self.logger.error(f"订单{order_code}处理异常: {e}")
                tb_str = traceback.format_exc()
                self.logger.error(f"详细错误: {tb_str}")

                # 将订单标记为失败状态（status=2），保留time_accept用于追踪
                try:
                    with connection.cursor() as cur:
                        sql = """
                            UPDATE orders_df
                            SET status = 2
                            WHERE code = %s AND status = 1
                        """
                        cur.execute(sql, (order_code,))
                        connection.commit()
                        self.logger.info(f'订单{order_code}异常后已标记为失败状态(status=2)，保留time_accept')
                except Exception as reset_e:
                    self.logger.error(f'订单{order_code}更新失败状态失败: {reset_e}')

                # 设置payment_id失败冷却期
                if payment_id:
                    # 在异常情况下，order_data可能不可用，所以只传递已知信息
                    order_info = {'code': order_code} if order_code else None
                    self.settlement.set_payment_id_failed(
                        payment_id,
                        f"系统异常: {str(e)}",
                        order_info,
                        status=3  # 3: 系统异常
                    )

                    # 🔥 记录失败详情到统一Hash（用于重复订单检测）
                    # 只有在order_data可用时才记录（防止异常发生在查询订单之前）
                    if order_data:
                        self.account_selector.record_payment_failure(
                            payment_id=payment_id,
                            amount=order_data['amount'],
                            to_account=order_data.get('payment_account', ''),
                            reason=f"系统异常: {str(e)}",
                            order_code=order_code
                        )

                return False

        except Exception as e:
            self.logger.error(f"处理订单{order_message}初始化异常: {e}")
            tb_str = traceback.format_exc()
            self.logger.error(f"详细错误: {tb_str}")
            return False

        finally:
            # 7. 释放所有锁和资源
            if connection:
                try:
                    connection.close()
                except:
                    pass

            # 释放 payment_id 锁
            if payment_id_lock_value and payment_id:
                self.account_selector.del_payment_id_lock(payment_id, payment_id_lock_value)

            # 释放账号锁
            if account_lock and account_id:
                self.account_selector.release_account_lock(account_id, account_lock)

            # 释放订单锁
            if order_lock_value and order_code:
                self.account_selector.del_lock(order_code, order_lock_value)




