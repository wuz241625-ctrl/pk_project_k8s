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
            self.mark_stale_claimed_orders_unknown(connection)

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
            if order_data.get('target_payment'):
                target_payment_ids = self._parse_payment_id_list(order_data.get('target_payment'))
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

    def _open_connection(self):
        return pymysql.connect(
            host=conf['mysql_host'],
            user=conf['mysql_user'],
            password=conf['mysql_password'],
            db=conf['mysql_database'],
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )

    def _claim_order(self, connection, order_data: Dict, selected_account: Dict) -> Optional[Dict]:
        """MySQL 原子抢单。抢不到就不能调用 JazzCash 官方出款。"""
        order_code = order_data['code']
        payment_id = selected_account['payment_id']
        partner_id = selected_account.get('partner_id')
        try:
            with connection.cursor() as cur:
                sql_claim = """
                    UPDATE orders_df
                    SET status = 1,
                        time_accept = NOW(),
                        payment_id = %s,
                        partner_id = %s
                    WHERE code = %s AND status = 0
                    LIMIT 1
                """
                cur.execute(sql_claim, (payment_id, partner_id, order_code))
                if cur.rowcount != 1:
                    connection.rollback()
                    self.logger.warning(f"订单{order_code}抢单失败，可能已被其他worker处理")
                    return None

                cur.execute("SELECT * FROM orders_df WHERE code = %s LIMIT 1", (order_code,))
                claimed_order = cur.fetchone()
                if not claimed_order:
                    connection.rollback()
                    self.logger.error(f"订单{order_code}抢单后查询失败")
                    return None

                connection.commit()
                self.logger.info(f"订单{order_code}抢单成功: payment_id={payment_id}, partner_id={partner_id}")
                return claimed_order
        except Exception as e:
            connection.rollback()
            self.logger.error(f"订单{order_code}抢单异常: {e}\n{traceback.format_exc()}")
            return None

    def _mark_payment_invalid(self, connection, payment_id: str, reason: str):
        try:
            with connection.cursor() as cur:
                sql = """
                    UPDATE payment
                    SET wallet_status = 0,
                        collection_status = 0,
                        payout_status = 0
                    WHERE id = %s
                      AND (wallet_status <> 0 OR collection_status <> 0 OR payout_status <> 0)
                    LIMIT 1
                """
                cur.execute(sql, (payment_id,))
            self.logger.warning(f"JazzCash payment_id={payment_id} 因 {reason} 已关闭三最终态")
        except Exception as e:
            self.logger.error(f"关闭 JazzCash payment_id={payment_id} 三最终态失败: {e}")

    def mark_stale_claimed_orders_unknown(self, connection, stale_minutes: int = 15) -> int:
        """把长时间停在执行中的 JazzCash 订单转人工确认，避免 worker 崩溃后永久卡单。"""
        try:
            with connection.cursor() as cur:
                sql = """
                    UPDATE orders_df od
                    JOIN payment p ON p.id = od.payment_id
                    SET od.status = 2,
                        od.sys_remark = %s
                    WHERE od.status = 1
                      AND od.time_accept IS NOT NULL
                      AND od.time_accept < DATE_SUB(NOW(), INTERVAL %s MINUTE)
                      AND (p.bank_type = 98 OR p.bank_type_id = 98)
                """
                remark = f"JazzCash执行中超过{stale_minutes}分钟，转人工确认"
                affected = cur.execute(sql, (remark, stale_minutes))
            connection.commit()
            if affected:
                self.logger.warning(f"JazzCash执行中超时订单已转人工确认: affected={affected}")
            return affected
        except Exception as e:
            connection.rollback()
            self.logger.error(f"JazzCash执行中超时巡检失败: {e}\n{traceback.format_exc()}")
            return 0

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
        """JazzCash 代付订单处理：与 EasyPaisa 保持同一抢单/执行/结算状态机。"""
        order_code = order_data['code']
        amount = Decimal(str(order_data['amount']))

        self.logger.info(f"开始处理代付订单: {order_code}, 金额: {amount}")

        if not selected_account:
            return {'success': False, 'message': '缺少预分配账号'}

        account_id = selected_account['phone']
        payment_id = selected_account['payment_id']
        order_lock_value = None
        account_lock = None
        payment_id_lock_value = None
        own_connection = False
        claimed_order = None

        try:
            risk_result = await self.check_payout_risk(order_data)
            if not risk_result['passed']:
                return {
                    'success': False,
                    'message': f"风控拦截: {risk_result.get('message', risk_result['reason'])}"
                }

            order_lock_value = self.account_selector.get_lock(order_code)
            if not order_lock_value:
                return {'success': False, 'message': f'订单{order_code}未抢到订单锁'}

            account_lock = await self.account_selector.acquire_account_lock(account_id, order_code)
            if not account_lock:
                return {'success': False, 'message': f'订单{order_code}账号{account_id}锁定失败'}

            payment_id_lock_value = self.account_selector.get_payment_id_lock(payment_id)
            if not payment_id_lock_value:
                return {'success': False, 'message': f'订单{order_code} payment_id={payment_id}锁定失败'}

            if not self.account_selector.check_account_release_time(payment_id):
                return {'success': False, 'message': f'payment_id={payment_id}仍在释放期，跳过'}

            if self.account_selector.is_account_recently_used(payment_id):
                return {'success': False, 'message': f'payment_id={payment_id}近期已使用，跳过'}

            amount_check = await self.account_selector.check_account_amount_limits(payment_id, amount)
            if not amount_check.get('passed', True):
                return {
                    'success': False,
                    'message': f'payment_id={payment_id}金额/日限额不通过: {amount_check}'
                }

            if hasattr(self.account_selector, 'check_payment_balance') and not self.account_selector.check_payment_balance(payment_id, amount):
                return {'success': False, 'message': f'payment_id={payment_id}余额不足，跳过'}

            if connection is None:
                connection = self._open_connection()
                own_connection = True

            claimed_order = self._claim_order(connection, order_data, selected_account)
            if not claimed_order:
                return {
                    'success': False,
                    'claimed': False,
                    'message': f'订单{order_code}抢单失败',
                }

            transfer_result = await self.transfer_executor._execute_jazzcash_transfer(claimed_order, selected_account)

            if transfer_result and transfer_result.get('success'):
                self.account_selector.record_account_usage(payment_id)
                self.account_selector.set_account_release_time(payment_id)

                self.settlement.qr_id = payment_id
                with connection.cursor() as cur:
                    balance_updated = self.account_selector.deduct_account_balance_in_transaction(
                        cur,
                        payment_id,
                        amount,
                    )
                    if not balance_updated:
                        connection.rollback()
                        return self._mark_unknown(connection, order_code, '官方已返回成功，但payment.balance余额不足或扣减失败，人工核对')
                    settled = self.settlement.handle_payout_success(connection, cur, claimed_order, transfer_result)
                if settled:
                    connection.commit()
                    self.redis.publish('order_df_notify', order_code)
                    if hasattr(self.account_selector, 'mark_order_cooldown_success'):
                        self.account_selector.mark_order_cooldown_success(order_code)
                    return {
                        'success': True,
                        'message': '转账成功',
                        'transaction_id': transfer_result.get('transaction_id'),
                        'account_used': account_id,
                        'payment_id': payment_id,
                        'partner_id': selected_account.get('partner_id'),
                        'payer_phone': transfer_result.get('payer_phone'),
                        'selected_account': selected_account
                    }

                connection.rollback()
                return self._mark_unknown(connection, order_code, '官方已返回成功，payment.balance扣减与结算事务失败，人工核对')

            self.account_selector.set_account_release_time(payment_id)

            if transfer_result is None:
                return self._mark_unknown(connection, order_code, 'JazzCash no response, manual review required')

            message = transfer_result.get('message', '')
            error_code = transfer_result.get('code')
            if transfer_result.get('account_invalid'):
                self._mark_payment_invalid(connection, payment_id, message or '501 account invalid')
                return self._mark_unknown(connection, order_code, f"501 account invalid: {message}")

            if transfer_result.get('reject'):
                return self._reject_order(connection, claimed_order, selected_account, transfer_result.get('reject_reason') or message)

            if error_code == 402:
                return self._handle_402(connection, claimed_order, selected_account, message)

            return self._mark_unknown(connection, order_code, f"JazzCash API code={error_code}: {message}")

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
            if connection and claimed_order:
                return self._mark_unknown(connection, order_code, 'API超时，设为待确认状态待人工核实')
            return {'success': False, 'unknown': True, 'message': 'API超时，未抢单或无连接'}
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
            if connection and claimed_order:
                return self._mark_unknown(connection, order_code, f'处理异常，人工待确认: {str(e)}')
            return {'success': False, 'unknown': True, 'message': f'处理异常: {str(e)}'}
        finally:
            if payment_id_lock_value:
                self.account_selector.del_payment_id_lock(payment_id, payment_id_lock_value)
            if account_lock:
                self.account_selector.release_account_lock(account_id, account_lock)
            if order_lock_value:
                self.account_selector.del_lock(order_code, order_lock_value)
            if hasattr(self.account_selector, 'release_selected_account'):
                try:
                    self.account_selector.release_selected_account(selected_account)
                except Exception:
                    pass
            if own_connection and connection:
                try:
                    connection.close()
                except Exception:
                    pass

    async def _process_single_order_via_state_machine(self, order_message: str) -> bool:
        """订单消息入口只负责读订单和选账号，执行/抢单/结算统一交给 process_payout_order。"""
        parts = order_message.split('_')
        if len(parts) < 2:
            self.logger.error(f"订单消息格式错误: {order_message}")
            return False

        order_code = parts[0]
        connection = None
        try:
            if not is_auto_payout_enabled(conf, self.logger):
                self.logger.warning(f"订单{order_code}处理前检测到MySQL自动代付开关关闭，停止处理")
                return False

            connection = self._open_connection()
            with connection.cursor() as cur:
                cur.execute('SELECT * FROM orders_df WHERE code = %s', (order_code,))
                order_data = cur.fetchone()

            if not order_data:
                self.logger.error(f'订单{order_code}不存在')
                return False
            if order_data.get('status') != 0:
                self.logger.info(f'订单{order_code}已被处理，状态: {order_data.get("status")}')
                return False

            amount = Decimal(str(order_data['amount']))
            target_account = order_data.get('payment_account', '')
            accounts = await self.account_selector.get_available_accounts(amount, target_account)
            target_payment = order_data.get('target_payment')
            if target_payment:
                target_payment_ids = self._parse_payment_id_list(target_payment)
                accounts = [account for account in accounts if str(account['payment_id']) in target_payment_ids]
            else:
                dedicated_payment_ids = set(self._fetch_mysql_dedicated_payment_ids())
                accounts = [account for account in accounts if str(account['payment_id']) not in dedicated_payment_ids]

            if not accounts:
                self.logger.info(f"订单{order_code} 暂无可用账号，不更新订单状态，等待下轮")
                return False

            result = await self.process_payout_order(order_data, selected_account=accounts[0])
            return bool(result and result.get('success'))
        except Exception as e:
            self.logger.error(f"处理订单{order_message}初始化异常: {e}\n{traceback.format_exc()}")
            return False
        finally:
            if connection:
                try:
                    connection.close()
                except Exception:
                    pass

    async def process_single_order_async(self, order_message: str) -> bool:
        """异步处理单个订单：只读单选号，执行链统一交给 process_payout_order。"""
        return await self._process_single_order_via_state_machine(order_message)
