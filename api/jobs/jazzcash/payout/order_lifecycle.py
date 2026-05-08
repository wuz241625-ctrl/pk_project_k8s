"""
JazzCash Order Lifecycle — Order processing pipeline, risk checks.
Extracted from jazzcash_auto_payout.py Phase 3 refactoring.
"""
import time
import asyncio
import pymysql
import traceback
from decimal import Decimal
from typing import Dict, List, Optional

from config import get_config
from jobs.auto_payout_state import is_auto_payout_enabled

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

    @staticmethod
    def _parse_payment_id_list(value) -> List[str]:
        if not value:
            return []
        raw_items = str(value).replace(' ', '').strip(',').split(',')
        payment_ids = []
        seen = set()
        for item in raw_items:
            payment_id = str(item).strip()
            if payment_id.isdigit() and payment_id not in seen:
                seen.add(payment_id)
                payment_ids.append(payment_id)
        return payment_ids

    def _fetch_mysql_dedicated_payment_ids(self) -> List[str]:
        connection = None
        try:
            connection = pymysql.connect(
                host=conf['mysql_host'],
                user=conf['mysql_user'],
                password=conf['mysql_password'],
                database=conf['mysql_database'],
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True,
            )
            with connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT target_payment
                    FROM merchant
                    WHERE target_payment IS NOT NULL
                      AND target_payment != ''
                    """
                )
                rows = cur.fetchall()
            dedicated_payment_ids = []
            for row in rows or []:
                dedicated_payment_ids.extend(
                    self._parse_payment_id_list(row.get('target_payment'))
                )
            return self._parse_payment_id_list(','.join(dedicated_payment_ids))
        except Exception as exc:
            self.logger.warning(f"读取MySQL专卡专户配置失败，按无全局独占码处理: {exc}")
            return []
        finally:
            if connection:
                connection.close()

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

                        # 从 MySQL payment.balance 获取高余额账号（余额 >= 最小订单金额）
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
                target_payment_ids = self._parse_payment_id_list(order_data['target_payment'])
                target_payment_filtered_accounts = [account for account in accounts if str(account['payment_id']) in target_payment_ids]
            else:
                dedicated_payment_ids = set(self._fetch_mysql_dedicated_payment_ids())
                target_payment_filtered_accounts = [account for account in accounts if str(account['payment_id']) not in dedicated_payment_ids]
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
                self.account_selector.release_selected_account(selected_account)
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
                self.account_selector.release_selected_account(selected_account)
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
                self.account_selector.release_selected_account(selected_account)
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
                    self.account_selector.release_selected_account(selected_account)
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
            if not is_auto_payout_enabled(conf, self.logger):
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

    def _mark_unknown(self, connection, order_code: str, reason: str) -> Dict:
        """未知出款结果进入人工待确认，绝不回到待处理池。"""
        reason_text = str(reason)
        reason_bytes = reason_text.encode('utf-8')
        if len(reason_bytes) > 255:
            reason_text = reason_bytes[:255].decode('utf-8', errors='ignore')
        try:
            with connection.cursor() as cur:
                sql = """
                    UPDATE orders_df
                    SET status = 2,
                        sys_remark = %s
                    WHERE code = %s AND status = 1
                    LIMIT 1
                """
                cur.execute(sql, (reason_text, order_code))
                affected = cur.rowcount
            connection.commit()
            self.logger.warning(f"订单{order_code}进入人工待确认(status=2), affected={affected}, reason={reason_text}")
            return {
                'success': False,
                'unknown': True,
                'message': reason_text,
                'affected': affected,
            }
        except Exception as e:
            connection.rollback()
            self.logger.error(f"订单{order_code}写入人工待确认失败: {e}\n{traceback.format_exc()}")
            return {'success': False, 'unknown': True, 'message': f'unknown update failed: {e}'}

    def _reject_order(self, connection, order_data: Dict, selected_account: Dict, reason: str,
                      retry_count: Optional[int] = None) -> Dict:
        result = self.settlement.reject_order_with_refund(order_data, connection, reason, selected_account)
        if result.get('reject'):
            if retry_count is not None:
                with connection.cursor() as cur:
                    cur.execute(
                        "UPDATE orders_df SET retry_count=%s WHERE code=%s AND status=-2 LIMIT 1",
                        (retry_count, order_data['code']),
                    )
            connection.commit()
            self.redis.publish('order_df_notify', order_data['code'])
            return {
                'success': False,
                'reject': True,
                'message': result.get('message', reason),
                'retry_count': retry_count,
            }
        connection.rollback()
        return {
            'success': False,
            'reject': False,
            'message': result.get('message', reason),
        }

    def _handle_402(self, connection, order_data: Dict, selected_account: Dict, reason: str) -> Dict:
        """402 是明确失败：最多重试 3 次，第 3 次驳回。"""
        order_code = order_data['code']
        current_retry_count = int(order_data.get('retry_count') or 0)
        new_retry_count = current_retry_count + 1
        if new_retry_count >= 3:
            self.logger.warning(f"订单{order_code} 402失败达到{new_retry_count}次，直接驳回")
            return self._reject_order(
                connection,
                order_data,
                selected_account,
                f"402 failed {new_retry_count} times: {reason}",
                retry_count=new_retry_count,
            )

        try:
            with connection.cursor() as cur:
                sql = """
                    UPDATE orders_df
                    SET retry_count = %s,
                        status = 0,
                        time_accept = NULL,
                        payment_id = NULL,
                        partner_id = NULL
                    WHERE code = %s AND status = 1
                    LIMIT 1
                """
                cur.execute(sql, (new_retry_count, order_code))
                affected = cur.rowcount
            if affected != 1:
                connection.rollback()
                return {'success': False, 'retry': False, 'message': '402 retry update skipped'}
            connection.commit()
            if hasattr(self.account_selector, 'record_payment_failure'):
                self.account_selector.record_payment_failure(
                    payment_id=selected_account['payment_id'],
                    amount=Decimal(str(order_data['amount'])),
                    to_account=order_data.get('payment_account', ''),
                    reason=reason,
                    order_code=order_code,
                )
            if hasattr(self.account_selector, 'set_order_cooldown'):
                self.account_selector.set_order_cooldown(
                    order_code,
                    selected_account.get('payment_id'),
                    reason,
                    {**order_data, 'retry_count': new_retry_count},
                    status=1,
                )
            self.logger.info(f"订单{order_code} 402失败第{new_retry_count}次，回到待处理池")
            return {
                'success': False,
                'retry': True,
                'retry_count': new_retry_count,
                'message': reason,
            }
        except Exception as e:
            connection.rollback()
            self.logger.error(f"订单{order_code}处理402重试失败: {e}\n{traceback.format_exc()}")
            return {'success': False, 'retry': False, 'message': f'402 retry exception: {e}'}

    # ========== 调度引擎 ==========

    async def process_payout_order(self, order_data: Dict, connection=None, selected_account: Dict = None) -> Dict:
        """代付订单处理"""
        order_code = order_data['code']
        amount = Decimal(str(order_data['amount']))

        self.logger.info(f"开始处理代付订单: {order_code}, 金额: {amount}")

        if not selected_account:
            return {'success': False, 'message': '缺少预分配账号'}

        account_id = selected_account['phone']

        try:
            risk_result = await self.check_payout_risk(order_data)
            if not risk_result['passed']:
                return {
                    'success': False,
                    'message': f"风控拦截: {risk_result.get('message', risk_result['reason'])}"
                }

            transfer_result = await self.transfer_executor._execute_jazzcash_transfer(order_data, selected_account)

            if transfer_result and transfer_result.get('success'):
                self.account_selector.record_account_usage(selected_account['payment_id'])
                self.settlement.update_account_balance_after_transfer(
                    payment_id=selected_account['payment_id'],
                    transfer_amount=amount
                )
                self.account_selector.set_account_release_time(selected_account['payment_id'])
                self.account_selector.release_selected_account(selected_account)

                return {
                    'success': True,
                    'message': '转账成功',
                    'transaction_id': transfer_result.get('transaction_id'),
                    'account_used': account_id,
                    'payment_id': selected_account['payment_id'],
                    'partner_id': selected_account.get('partner_id'),
                    'payer_phone': transfer_result.get('payer_phone'),
                    'selected_account': selected_account
                }

            self.account_selector.set_account_release_time(selected_account['payment_id'])
            self.account_selector.release_selected_account(selected_account)

            if transfer_result is None:
                return {
                    'success': False,
                    'unknown': True,
                    'message': 'JazzCash API无响应或脚本异常，进入人工待确认',
                    'payment_id': selected_account['payment_id'],
                    'partner_id': selected_account.get('partner_id')
                }

            message = transfer_result.get('message', '')
            error_code = transfer_result.get('code')
            if error_code == 402:
                return {
                    'success': False,
                    'code': 402,
                    'message': message,
                    'payment_id': selected_account['payment_id'],
                    'partner_id': selected_account.get('partner_id')
                }

            return {
                'success': False,
                'unknown': True,
                'code': error_code,
                'message': f"JazzCash出款结果未知(code={error_code})，进入人工待确认: {message}",
                'payment_id': selected_account['payment_id'],
                'partner_id': selected_account.get('partner_id')
            }

        except asyncio.TimeoutError:
            self.logger.warning(f"订单{order_code}API超时，进入人工待确认")
            try:
                self.transaction_logger.log_complete_transaction(
                    order_data,
                    selected_account,
                    {},
                    {},
                    "early_exception_timeout",
                    error_message="订单处理超时，进入人工待确认避免重复代付",
                    start_time=time.time(),
                    before_balance=None,
                    process_details={'exception_type': 'asyncio.TimeoutError', 'exception_stage': 'process_payout_order'}
                )
            except Exception as log_e:
                self.logger.warning(f"记录超时异常日志失败: {log_e}")
            return {
                'success': False,
                'unknown': True,
                'message': 'API超时，设为待确认状态待人工核实',
                'payment_id': selected_account['payment_id'],
                'partner_id': selected_account.get('partner_id')
            }
        except Exception as e:
            self.logger.error(f"订单{order_code}处理异常: {e}")
            try:
                self.transaction_logger.log_complete_transaction(
                    order_data,
                    selected_account,
                    {},
                    {},
                    "early_exception",
                    error_message=f"订单处理异常，进入人工待确认避免重复代付: {str(e)}",
                    start_time=time.time(),
                    before_balance=None,
                    process_details={'exception_type': type(e).__name__, 'exception_stage': 'process_payout_order', 'exception_detail': str(e)}
                )
            except Exception as log_e:
                self.logger.warning(f"记录处理异常日志失败: {log_e}")
            return {
                'success': False,
                'unknown': True,
                'message': f'处理异常，设为待确认状态待人工核实: {str(e)}',
                'payment_id': selected_account['payment_id'],
                'partner_id': selected_account.get('partner_id')
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

            if not is_auto_payout_enabled(conf, self.logger):
                self.logger.warning(f"订单{order_code}处理前检测到MySQL自动代付开关关闭，停止处理")
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

                    # 4. 原子抢单：只有 status=0 才能进入处理中，同时绑定本次出款账号。
                    partner_id = selected_account.get('partner_id')
                    sql = """
                        UPDATE orders_df
                        SET status = 1,
                            time_accept = NOW(),
                            payment_id = %s,
                            partner_id = %s
                        WHERE code = %s AND status = 0
                        LIMIT 1
                    """
                    cur.execute(sql, (payment_id, partner_id, order_code))
                    affected_rows = cur.rowcount
                    if affected_rows == 0:
                        self.logger.warning(f'订单{order_code}状态已不是0，可能已被其他进程处理，跳过')
                        return False
                    connection.commit()
                    self.logger.info(f'订单{order_code}抢单成功: status=1, payment_id={payment_id}, partner_id={partner_id}')

                    # 🔥 5. 执行转账（传入已选择的账号）
                    result = await self.process_payout_order(
                        order_data,
                        connection,
                        selected_account=selected_account
                    )

                    # 6. 根据处理结果分别处理。成功态只能由 settlement 用 status=1 守卫推进到 status=3。
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
                                            self._mark_unknown(
                                                success_connection,
                                                order_code,
                                                'JazzCash success settlement failed, manual review required'
                                            )
                                            success_result = False
                            finally:
                                if success_connection:
                                    success_connection.close()

                        except Exception as e:
                            self.logger.error(f"订单{order_code}调用success处理异常: {e}")
                            self.logger.error(traceback.format_exc())
                            success_result = False

                    else:
                        if 'emergency_stop' in result.get('message', '') or 'system紧急停机' in result.get('message', ''):
                            self.logger.warning(f'⚠️ 订单{order_code}遇到紧急停机，重置为待处理状态: {result["message"]}')
                            sql = """
                                UPDATE orders_df
                                SET status = 0,
                                    time_accept = NULL,
                                    payment_id = NULL,
                                    partner_id = NULL
                                WHERE code = %s AND status = 1
                                LIMIT 1
                            """
                            cur.execute(sql, (order_code,))
                            connection.commit()
                            self.logger.info(f'订单{order_code}已重置为待处理状态(status=0)')
                            return False
                        elif result.get('code') == 402:
                            handled = self._handle_402(connection, order_data, selected_account, result.get('message', '402 failed'))
                            return bool(handled.get('success'))
                        else:
                            unknown_result = self._mark_unknown(
                                connection,
                                order_code,
                                result.get('message', 'JazzCash出款结果未知，人工待确认')
                            )
                            if payment_id:
                                self.settlement.set_payment_id_failed(
                                    payment_id,
                                    unknown_result.get('message', '人工待确认'),
                                    order_data,
                                    status=2
                                )
                                self.account_selector.record_payment_failure(
                                    payment_id=payment_id,
                                    amount=order_data['amount'],
                                    to_account=order_data.get('payment_account', ''),
                                    reason=unknown_result.get('message', '人工待确认'),
                                    order_code=order_code
                                )
                            return False

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
