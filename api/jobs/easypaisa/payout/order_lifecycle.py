"""OrderLifecycle — complete order processing flow and cooldown logic.

Extracted from auto_payout.py (lines 2807-3371, 3517-3730, 4582-5141).
"""
import json
import time
import asyncio
import traceback
import secrets
import pymysql
from decimal import Decimal
from datetime import datetime
from typing import Dict, List, Optional


class OrderLifecycle:
    def __init__(self, redis_client, logger, conf: dict, REDIS_KEYS: dict,
                 account_selector, transfer_executor, settlement, transaction_logger):
        self.redis = redis_client
        self.logger = logger
        self.conf = conf
        self.REDIS_KEYS = REDIS_KEYS
        self.account_selector = account_selector
        self.transfer_executor = transfer_executor
        self.settlement = settlement
        self.transaction_logger = transaction_logger

    # ========== Payment ID Failure Cooldown ==========

    def set_payment_id_failed(self, payment_id, reason="处理失败", order_data=None, status=1):
        """设置payment_id失败状态 - 20分钟冷却期

        Args:
            payment_id: Payment ID
            reason: 失败原因
            order_data: 完整订单数据（可选）
            status: 状态类型 - 1: 真正失败, 2: 按成功处理, 3: 系统异常
        """
        try:
            import time

            # 安全转换数值类型为JSON可序列化格式
            def safe_numeric(value):
                """安全转换数值类型，处理Decimal等不可JSON序列化的类型"""
                if value is None:
                    return None
                if isinstance(value, Decimal):
                    return float(value)
                if isinstance(value, (int, float)):
                    return value
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return str(value)

            failed_key = f'{self.REDIS_KEYS["payment_id_failed_prefix"]}{payment_id}'

            # 构造JSON格式的Value
            failed_info = {
                'payment_id': payment_id,
                'reason': reason,
                'created_time': time.time(),
                'expire_time': time.time() + 1200,  # 20分钟后过期
                'status': status
            }

            # 如果有订单数据，添加到JSON中
            if order_data:
                failed_info.update({
                    'order_code': order_data.get('code'),
                    'amount': safe_numeric(order_data.get('amount')),
                    'payment_account': order_data.get('payment_account'),
                    'name': order_data.get('name'),
                    'bank_code': order_data.get('bank_code'),
                    'time_created': str(order_data.get('time_accept', '')),
                    'user_id': order_data.get('user_id'),
                    'channel_id': order_data.get('channel_id')
                })

            # 设置20分钟冷却期，Value为JSON格式
            self.redis.setex(failed_key, 1200, json.dumps(failed_info, ensure_ascii=False))

            self.logger.info(f"Payment ID {payment_id} 设置失败冷却期20分钟: {reason}")

            return True
        except Exception as e:
            self.logger.error(f'设置payment_id失败状态失败: {e}')
            return False

    # ========== 订单冷却期管理机制 ==========

    def is_order_in_cooldown(self, order_code: str) -> bool:
        """检查订单是否在冷却期内"""
        try:
            hash_key = self.REDIS_KEYS['easypaisa_order_cooldown_hash']
            cooldown_info_str = self.redis.hget(hash_key, order_code)

            if cooldown_info_str:
                cooldown_info = json.loads(cooldown_info_str.decode())
                current_time = time.time()

                if current_time < cooldown_info['expire_time']:
                    # 仍在冷却期内
                    remaining_minutes = (cooldown_info['expire_time'] - current_time) / 60
                    self.logger.info(f"订单{order_code}在冷却期内，剩余{remaining_minutes:.1f}分钟: {cooldown_info['reason']}")
                    return True
                else:
                    # 冷却期已过期，标记为可处理状态，但不删除记录
                    if cooldown_info.get('status') != 'expired':
                        cooldown_info['status'] = 'expired'
                        self.redis.hset(hash_key, order_code, json.dumps(cooldown_info, ensure_ascii=False))
                        self.logger.info(f"订单{order_code}冷却期已过期，标记为可处理状态（等级{cooldown_info.get('cooldown_level', 0)}）")
                    return False

            return False
        except Exception as e:
            self.logger.error(f"检查订单{order_code}冷却期异常: {e}")
            return False  # 异常时允许处理

    def set_order_cooldown(self, order_code: str, payment_id: str, reason: str,
                           order_data: dict, status: int = 1):
        """设置订单冷却期（支持累加）

        Args:
            payment_id: payment_id，如果没有可用账号可传入None或"no_account"
            status: 1=明确失败, 2=按成功处理, 3=超限异常按成功处理
        """
        try:
            import time
            hash_key = self.REDIS_KEYS['easypaisa_order_cooldown_hash']
            current_time = time.time()

            # 尝试获取现有记录
            existing_info_str = self.redis.hget(hash_key, order_code)

            if existing_info_str:
                # 存在历史记录，累加冷却等级
                existing_info = json.loads(existing_info_str.decode())
                cooldown_level = existing_info.get('cooldown_level', 0) + 1
                total_failures = existing_info.get('total_failures', 0) + 1
                failure_history = existing_info.get('failure_history', [])
                first_failure_time = existing_info.get('first_failure_time', current_time)
            else:
                # 首次失败
                cooldown_level = 1
                total_failures = 1
                failure_history = []
                first_failure_time = current_time

            # 计算冷却时间
            if status == 3:  # 超限异常按成功处理，不设置实际冷却期
                cooldown_minutes = 0
                expire_time = current_time  # 立即过期，不影响后续处理
            else:
                cooldown_minutes = self.calculate_cooldown_minutes(cooldown_level)
                expire_time = current_time + (cooldown_minutes * 60)

            # 添加到失败历史
            failure_history.append({
                "time": current_time,
                "reason": reason,
                "cooldown_minutes": cooldown_minutes,
                "retry_count": order_data.get('retry_count', 0)
            })

            # 限制历史记录数量（避免无限增长）
            if len(failure_history) > 10:
                failure_history = failure_history[-10:]

            # 处理payment_id为None的情况（如没有可用账号）
            safe_payment_id = payment_id if payment_id is not None else "no_account"

            cooldown_info = {
                'order_code': order_code,
                'payment_id': safe_payment_id,
                'reason': reason,
                'created_time': current_time,
                'expire_time': expire_time,
                'cooldown_level': cooldown_level,
                'cooldown_minutes': cooldown_minutes,
                'total_failures': total_failures,
                'last_failure_time': current_time,
                'first_failure_time': first_failure_time,
                'failure_history': failure_history,
                'status': 'max_retry_final' if status == 3 else 'active',
                'order_amount': float(order_data.get('amount', 0)),
                'current_retry_count': order_data.get('retry_count', 0),
                'record_type': status
            }

            # 存储到Hash表
            self.redis.hset(hash_key, order_code, json.dumps(cooldown_info, ensure_ascii=False))

            if status == 3:
                self.logger.info(f"订单{order_code}超限终结记录: 等级{cooldown_level}, 总失败{total_failures}次, payment_id={safe_payment_id}, 仅用于统计: {reason}")
            else:
                self.logger.info(f"订单{order_code}设置冷却期: 等级{cooldown_level}, 时长{cooldown_minutes}分钟, 总失败{total_failures}次, payment_id={safe_payment_id}: {reason}")

        except Exception as e:
            self.logger.error(f"设置订单{order_code}冷却期异常: {e}")

    def calculate_cooldown_minutes(self, level: int) -> int:
        """根据冷却等级计算时间（支持动态配置，不限等级数量）

        规则：
        - 如果 level 在配置范围内，使用对应配置
        - 如果 level 超过配置数量，使用最后一个配置的时间（循环冷却）
        - 读取配置失败时使用默认值
        """
        try:
            # 从 Redis 读取配置
            config_key = self.REDIS_KEYS.get('easypaisa_order_cooldown_config')

            if config_key:
                config_str = self.redis.get(config_key)

                if config_str:
                    # 处理 bytes 类型（Redis 可能返回 bytes 或 str）
                    if isinstance(config_str, bytes):
                        config_str = config_str.decode('utf-8')

                    config = json.loads(config_str)
                    levels_config = config.get('levels', [])

                    if levels_config:
                        # 查找匹配的等级配置
                        for level_config in levels_config:
                            if level_config['level'] == level:
                                minutes = level_config['minutes']
                                self.logger.info(f"[订单冷却期] 使用配置: 等级{level} = {minutes}分钟")
                                return minutes

                        # 超过最大等级，使用最后一个配置（支持无限等级）
                        max_configured_level = max([lc['level'] for lc in levels_config])
                        if level > max_configured_level:
                            last_config = levels_config[-1]
                            minutes = last_config['minutes']
                            self.logger.info(
                                f"[订单冷却期] 等级{level}超过配置范围(最大{max_configured_level})，"
                                f"使用最后一级配置: {minutes}分钟"
                            )
                            return minutes

        except json.JSONDecodeError as e:
            self.logger.warning(f"[订单冷却期] JSON解析失败，使用默认值: {e}")
        except Exception as e:
            self.logger.warning(f"[订单冷却期] 读取配置失败，使用默认值: {e}")

        # 默认值（向后兼容）
        default_levels = [
            {"level": 1, "minutes": 30},
            {"level": 2, "minutes": 120},
            {"level": 3, "minutes": 360},
            {"level": 4, "minutes": 1440}
        ]

        # 查找匹配的默认等级
        for default_level in default_levels:
            if default_level['level'] == level:
                self.logger.info(f"[订单冷却期] 使用默认配置: 等级{level} = {default_level['minutes']}分钟")
                return default_level['minutes']

        # 超出默认配置范围，使用最后一个默认值
        last_default_minutes = default_levels[-1]['minutes']
        self.logger.info(f"[订单冷却期] 等级{level}超出默认范围，使用最后一级默认值: {last_default_minutes}分钟")
        return last_default_minutes

    def mark_order_cooldown_success(self, order_code: str):
        """标记订单成功处理，更新冷却记录状态"""
        try:
            import time
            hash_key = self.REDIS_KEYS['easypaisa_order_cooldown_hash']
            cooldown_info_str = self.redis.hget(hash_key, order_code)

            if cooldown_info_str:
                # 订单有失败历史，更新状态为成功
                cooldown_info = json.loads(cooldown_info_str.decode())
                cooldown_info['status'] = 'success'
                cooldown_info['success_time'] = time.time()

                # 更新记录状态，但不删除（用于统计分析）
                self.redis.hset(hash_key, order_code, json.dumps(cooldown_info, ensure_ascii=False))

                self.logger.info(f"订单{order_code}成功处理，更新冷却记录状态为success（等级{cooldown_info.get('cooldown_level', 0)}）")
            else:
                # 订单没有失败历史（正常情况），无需冷却记录
                self.logger.debug(f"订单{order_code}成功处理，无失败历史记录（正常情况）")
        except Exception as e:
            self.logger.error(f"标记订单{order_code}成功状态异常: {e}")

    def filter_cooldown_orders(self, orders: List[Dict]) -> List[Dict]:
        """批量过滤冷却期内的订单"""
        if not orders:
            return orders

        try:
            import time
            hash_key = self.REDIS_KEYS['easypaisa_order_cooldown_hash']
            current_time = time.time()
            filtered_orders = []
            cooldown_details = []

            # 批量获取所有订单的冷却信息
            order_codes = [order['code'] for order in orders]

            # 使用Redis pipeline提高批量查询性能
            pipe = self.redis.pipeline()
            for order_code in order_codes:
                pipe.hget(hash_key, order_code)

            cooldown_results = pipe.execute()

            # 检查每个订单的冷却状态
            for i, order in enumerate(orders):
                order_code = order['code']
                cooldown_info_str = cooldown_results[i]

                if cooldown_info_str:
                    try:
                        cooldown_info = json.loads(cooldown_info_str.decode())

                        # 超限终结记录不参与冷却期检查
                        if cooldown_info.get('status') == 'max_retry_final':
                            pass
                        elif current_time < cooldown_info['expire_time']:
                            # 仍在冷却期内，跳过此订单
                            remaining_minutes = (cooldown_info['expire_time'] - current_time) / 60
                            cooldown_details.append({
                                'order_code': order_code,
                                'remaining_minutes': remaining_minutes,
                                'reason': cooldown_info.get('reason', '未知'),
                                'level': cooldown_info.get('cooldown_level', 0)
                            })
                            continue
                        else:
                            # 冷却期已过期，标记为可处理状态（批量更新）
                            if cooldown_info.get('status') != 'expired':
                                cooldown_info['status'] = 'expired'
                                self.redis.hset(hash_key, order_code, json.dumps(cooldown_info, ensure_ascii=False))

                    except (json.JSONDecodeError, KeyError) as e:
                        # JSON解析错误，删除异常记录，允许处理
                        self.logger.warning(f"订单{order_code}冷却期记录格式异常，删除记录: {e}")
                        self.redis.hdel(hash_key, order_code)

                # 添加到可处理订单列表
                filtered_orders.append(order)

            # 记录冷却期详情（debug级别）
            if cooldown_details:
                for detail in cooldown_details:
                    self.logger.debug(f"订单{detail['order_code']}在冷却期内({detail['remaining_minutes']:.1f}分钟)，等级{detail['level']}: {detail['reason']}")

            return filtered_orders

        except Exception as e:
            # Redis访问异常时，返回原始订单列表（降级处理）
            self.logger.error(f"批量检查订单冷却期异常，返回原始订单列表: {e}")
            return orders

    # ========== 风控控制器 ==========
    async def check_payout_risk(self, order_data: Dict) -> Dict:
        """风控检查"""
        try:
            # 检查紧急停机
            emergency_stop = self.redis.get(self.REDIS_KEYS['easypaisa_emergency_stop'])
            if emergency_stop == b"1" or emergency_stop == "1":
                return {'passed': False, 'reason': 'emergency_stop', 'message': '系统紧急停机'}

            amount = Decimal(str(order_data['amount']))

            # 基础金额检查
            if amount < Decimal('0.1'):
                return {'passed': False, 'reason': 'amount_too_small', 'message': '单笔金额过小'}

            # 检查系统负载
            active_orders_key = 'easypaisa_active_orders_count'
            active_count = self.redis.get(active_orders_key)
            if active_count and int(active_count.decode()) > 100:
                return {'passed': False, 'reason': 'system_overload', 'message': '系统负载过高'}

            return {'passed': True}

        except Exception as e:
            self.logger.error(f"风控检查异常: {e}")
            return {'passed': True, 'message': '风控检查异常，放行处理'}

    # ========== 订单处理主流程 ==========

    def _open_connection(self):
        return pymysql.connect(
            host=self.conf['mysql_host'],
            user=self.conf['mysql_user'],
            password=self.conf['mysql_password'],
            db=self.conf['mysql_database'],
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )

    def _claim_order(self, connection, order_data: Dict, selected_account: Dict) -> Optional[Dict]:
        """MySQL 原子抢单。抢不到就不能调用官方出款。"""
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

    def _mark_unknown(self, connection, order_code: str, reason: str) -> Dict:
        """未知结果进入人工待确认，绝不回到待处理池。"""
        max_remark_bytes = 255
        reason_bytes = str(reason).encode('utf-8')
        if len(reason_bytes) > max_remark_bytes:
            sys_remark = reason_bytes[:max_remark_bytes].decode('utf-8', errors='ignore')
        else:
            sys_remark = str(reason)
        try:
            with connection.cursor() as cur:
                sql = """
                    UPDATE orders_df
                    SET status = 2,
                        sys_remark = %s
                    WHERE code = %s AND status = 1
                    LIMIT 1
                """
                cur.execute(sql, (sys_remark, order_code))
                affected = cur.rowcount
            connection.commit()
            self.logger.warning(f"订单{order_code}进入人工待确认(status=2), affected={affected}, reason={sys_remark}")
            return {
                'success': False,
                'unknown': True,
                'message': sys_remark,
                'affected': affected,
            }
        except Exception as e:
            connection.rollback()
            self.logger.error(f"订单{order_code}写入人工待确认失败: {e}\n{traceback.format_exc()}")
            return {'success': False, 'unknown': True, 'message': f'unknown update failed: {e}'}

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
            self.logger.warning(f"EasyPaisa payment_id={payment_id} 因 {reason} 已关闭三最终态")
        except Exception as e:
            self.logger.error(f"关闭 EasyPaisa payment_id={payment_id} 三最终态失败: {e}")

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
            self.set_order_cooldown(order_code, selected_account.get('payment_id'), reason, {
                **order_data,
                'retry_count': new_retry_count,
            })
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

    async def process_payout_order(self, order_data: Dict, connection=None, selected_account: Dict = None) -> Dict:
        """代付订单处理"""
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
            # 1. 风控检查
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

            try:
                # 6. 执行EasyPaisa转账
                transfer_result = await self.transfer_executor._execute_easypaisa_transfer(claimed_order, selected_account)

                if transfer_result and transfer_result['success']:
                    # 转账成功，记录账号使用时间（动态冷却期）
                    self.account_selector.record_account_usage(selected_account['payment_id'])

                    # 转账成功后立即扣减Redis余额
                    self.account_selector.update_account_balance_after_transfer(
                        payment_id=selected_account['payment_id'],
                        transfer_amount=amount
                    )

                    # 转账成功，设置账号释放时间（从配置读取）
                    self.account_selector.set_account_release_time(selected_account['payment_id'])

                    self.settlement.qr_id = selected_account['payment_id']
                    with connection.cursor() as cur:
                        settled = self.settlement.handle_payout_success(connection, cur, claimed_order, transfer_result)
                    if settled:
                        connection.commit()
                        self.redis.publish('order_df_notify', order_code)
                        self.mark_order_cooldown_success(order_code)
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
                    connection.rollback()
                    return self._mark_unknown(connection, order_code, 'success settlement failed, manual review required')
                elif transfer_result is None:
                    self.account_selector.set_account_release_time(selected_account['payment_id'])
                    return self._mark_unknown(connection, order_code, 'EasyPaisa no response, manual review required')
                else:
                    # 转账失败，根据错误码区分处理
                    message = transfer_result.get('message', '')
                    error_code = transfer_result.get('code')
                    is_reject = transfer_result.get('reject', False)

                    self.account_selector.set_account_release_time(selected_account['payment_id'])

                    # 兼容历史返回；当前 402 只按重试次数处理。
                    if is_reject:
                        return self._reject_order(connection, claimed_order, selected_account, transfer_result.get('reject_reason') or message)

                    if error_code == 402:
                        return self._handle_402(connection, claimed_order, selected_account, message)

                    if transfer_result.get('account_invalid'):
                        self._mark_payment_invalid(connection, selected_account['payment_id'], message or '501 account invalid')
                        return self._mark_unknown(connection, order_code, f"501 account invalid: {message}")

                    return self._mark_unknown(connection, order_code, f"API code={error_code}: {message}")

            finally:
                pass

        except asyncio.TimeoutError:
            self.logger.warning(f"订单{order_code}API超时，进入人工待确认")

            # 记录操作日志（早期异常 - 超时）
            try:
                account_info = locals().get('selected_account', {'phone': 'unknown', 'payment_id': None})
                self.transaction_logger.log_complete_transaction(
                    order_data,
                    account_info,
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

            # 记录操作日志（早期异常 - 通用异常）
            try:
                account_info = locals().get('selected_account', {'phone': 'unknown', 'payment_id': None})
                self.transaction_logger.log_complete_transaction(
                    order_data,
                    account_info,
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
            if own_connection and connection:
                try:
                    connection.close()
                except Exception:
                    pass
