"""
JazzCash Account Selector — Account selection, locks, balance checks, cooldown.
Extracted from jazzcash_auto_payout.py Phase 3 refactoring.
"""
import time
import json
import uuid
import asyncio
import secrets
import aiohttp
import logging
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from config import get_config
from jobs.common.db import DBConnection
from application.payment_eligibility import payout_sql_condition
from application.jazzcash_gateway import build_form_body

conf = get_config()


class AccountSelector:
    """Handles account selection, locking, balance checks, and cooldown logic."""

    def __init__(self, redis, logger, config):
        self.redis = redis
        self.logger = logger
        self.config = config
        self.REDIS_KEYS = config.get('redis_keys', {})
        self.db = config.get('db') or DBConnection(conf)
        self.db_provider = config.get('db_provider')
        self.lock_time = config.get('lock_time', 120)
        self.api_url = config.get('jazzcash_api_url', 'http://34.150.42.92:84')
        self.user_id = config.get('jazzcash_user_id', 'ba08c3c0e4f546ad92dd2c2e8542ca36')
        self.secret_key = config.get('jazzcash_secret_key', 'ca45b35e132b46b9b68dd55f1ab077de')
        # Cross-module reference (set by orchestrator after construction)
        self.transfer_executor = None

    def _get_db_connection(self):
        if callable(self.db_provider):
            return self.db_provider()
        return self.db.connection

    async def check_account_online_status(self, payment_id: str) -> bool:
        """
        防护机制1: 检查账号代付接单资格。

        JazzCash 代付接单资格只读 MySQL payout_status。上游 isLogined 只能作为健康观测，
        不能覆盖 MySQL final state。
        """
        try:
            payment_info = self.get_phone_by_payment_id(payment_id)
            if not payment_info or not payment_info.get('phone'):
                self.logger.warning(f"payment_id {payment_id} 不满足 MySQL payout_status=1，账号不可代付")
                return False

            self.logger.debug(
                f"payment_id {payment_id} 满足 MySQL payout_status=1，phone={payment_info['phone']}"
            )
            return True

        except Exception as e:
            self.logger.error(f"检查账号payment_id:{payment_id}在线状态失败: {e}")
            return False

    async def _check_account_online_via_api(self, account_id: str) -> Optional[bool]:
        """
        通过JazzCash API实时检查账号在线状态

        Returns:
            True: 在线
            False: 离线
            None: API检查失败
        """
        try:
            # 构建isLogined请求
            import uuid
            request_uuid = str(uuid.uuid4())

            inner_payload = {
                "id": request_uuid,
                "action": "isLogined",
                "payload": {
                    "account_id": account_id
                }
            }

            self.logger.info(f"账号{account_id} 开始API在线状态检查，请求UUID: {request_uuid}")

            # 调用API查询方法
            response = await self.transfer_executor._call_jazzcash_api_query(inner_payload, account_id)

            # 打印完整的API响应
            self.logger.info(f"账号{account_id} isLogined API响应: {response}")

            if response:
                code = response.get('code')
                data = response.get('data')
                msg = response.get('msg', '')

                # 打印具体的code和data值
                self.logger.info(f"账号{account_id} API响应解析: code={code}, data={data}, msg={msg}")

                if code == 200 and data is True:
                    self.logger.info(f"账号{account_id} API检查结果：在线")
                    return True
                elif code == 403 or data is False:
                    self.logger.info(f"账号{account_id} API检查结果：离线")
                    return False
                else:
                    self.logger.warning(f"账号{account_id} API返回未知状态: code={code}, data={data}, msg={msg}")
                    return None
            else:
                self.logger.warning(f"账号{account_id} API检查无响应")
                return None

        except Exception as e:
            self.logger.error(f"账号{account_id} API在线状态检查异常: {e}")
            return None

    def _is_pakistan_mobile_number(self, account_number: str) -> bool:
        """
        判断是否为巴基斯坦手机号（JazzCash/EasyPaisa账号格式）

        巴基斯坦手机号格式：
        - 以 03 开头
        - 总共11位数字
        - 格式：03XXXXXXXXX
        """
        if not account_number:
            return False

        # 移除所有非数字字符
        clean_number = ''.join(filter(str.isdigit, account_number))

        # 检查格式：11位数字，以03开头
        if len(clean_number) == 11 and clean_number.startswith('03'):
            self.logger.debug(f"账号{account_number} 识别为巴基斯坦手机号")
            return True

        self.logger.debug(f"账号{account_number} 识别为银行账号（长度:{len(clean_number)}, 开头:{clean_number[:2] if len(clean_number) >= 2 else clean_number}）")
        return False


    def get_phone_by_payment_id(self, payment_id):
        """通过payment_id查询手机号和相关信息"""
        import time

        start_time = time.time()
        self.logger.info(f"[AutoPayout] 开始查询payment_id: {payment_id} 的详细信息")

        try:
            connection = self._get_db_connection()

            try:
                with connection.cursor() as cur:
                    sql = """
                        SELECT phone, account, name, bank_type, bank_type_id, partner_id,
                               wallet_status, payout_status
                        FROM payment
                        WHERE id = %s
                          AND payout_status = 1
                          AND (bank_type = 98 OR bank_type_id = 98)
                    """
                    self.logger.info(f"[AutoPayout] 执行SQL查询: payment_id={payment_id}")
                    self.logger.info(f"[AutoPayout] SQL语句: {sql.strip()}")
                    self.logger.info(f"[AutoPayout] 查询条件: payout_status=1 AND bank_type=98 (只查询JazzCash可代付账号)")

                    query_start = time.time()
                    cur.execute(sql, payment_id)
                    result = cur.fetchone()
                    query_time = time.time() - query_start

                    if result:
                        self.logger.info(f"[AutoPayout] 查询成功! payment_id={payment_id}, 查询耗时: {query_time:.3f}s")
                        self.logger.info(f"[AutoPayout] 查询结果:")
                        self.logger.info(f"   手机号: {result['phone']}")
                        self.logger.info(f"   账号: {result['account']}")
                        self.logger.info(f"   姓名: {result['name']}")
                        self.logger.info(f"   银行类型: {result['bank_type']}")
                        self.logger.info(f"   合作伙伴ID: {result['partner_id']}")
                        self.logger.info(f"   wallet_status: {result['wallet_status']}")
                        self.logger.info(f"   payout_status: {result['payout_status']}")
                        self.logger.info(f"   [AutoPayout] 账号符合使用条件，可用于自动代付")
                        return result
                    else:
                        self.logger.warning(f"[AutoPayout] payment_id {payment_id} 查询无结果")

                        # 检查是否存在但状态不符合条件
                        check_sql = "SELECT wallet_status, payout_status FROM payment WHERE id = %s"
                        self.logger.info(f"[AutoPayout] 检查payment_id是否存在但状态不合规...")
                        cur.execute(check_sql, payment_id)
                        check_result = cur.fetchone()
                        if check_result:
                            self.logger.warning(
                                f"[AutoPayout] payment_id {payment_id} 存在但不可代付: "
                                f"wallet_status={check_result['wallet_status']}, "
                                f"payout_status={check_result['payout_status']}"
                            )
                            self.logger.warning("[AutoPayout] 代付接单资格只看 payout_status=1")
                        else:
                            self.logger.warning(f"[AutoPayout] payment_id {payment_id} 在数据库中不存在")
                        return None
            finally:
                connection.commit()

        except Exception as e:
            total_time = time.time() - start_time
            self.logger.error(f"[AutoPayout] 查询payment_id {payment_id} 失败: {e}, 耗时: {total_time:.3f}s")
            import traceback
            self.logger.error(f"[AutoPayout] 详细错误信息: {traceback.format_exc()}")
            return None


    def get_payout_final_state_accounts(self, limit=20) -> List[Dict]:
        """从 MySQL payout_status=1 读取 JazzCash 代付候选账号。"""
        try:
            connection = self._get_db_connection()
            try:
                with connection.cursor() as cur:
                    sql = """
                        SELECT id, phone, account, name, bank_type, bank_type_id, partner_id,
                               wallet_status, payout_status
                        FROM payment
                        WHERE payout_status = 1
                          AND (bank_type = 98 OR bank_type_id = 98)
                        ORDER BY id
                        LIMIT %s
                    """
                    cur.execute(sql, (limit,))
                    rows = cur.fetchall() or []
                    return [
                        {
                            'payment_id': str(row['id']),
                            'phone': row['phone'],
                            'account': row.get('account', ''),
                            'name': row.get('name', ''),
                            'bank_type': row.get('bank_type', ''),
                            'partner_id': row.get('partner_id'),
                        }
                        for row in rows
                        if row.get('phone')
                    ]
            finally:
                connection.commit()
        except Exception as e:
            self.logger.error(f"从 MySQL payout_status 获取JazzCash代付账号失败: {e}")
            return []

    def release_selected_account(self, account_info):
        """保留给订单生命周期调用的释放钩子；MySQL 调度不维护 Redis 账号队列。"""
        if account_info:
            self.logger.debug(f"账号{account_info.get('payment_id')} 使用 MySQL 调度，无需回写 Redis 队列")
        return True

    async def check_account_amount_limits(self, payment_id: str, amount: Decimal) -> Dict:
        """
        防护机制5: 检查账号的金额限制和接单限额
        改用payment表现有的限额字段，如果字段为0或空则不控制
        balance_limit：单笔最高金额限制
        """
        try:
            connection = self._get_db_connection()

            try:
                with connection.cursor() as cur:
                    # ===== 旧代码：查询全局风控配置参数 (已注释) =====
                    # sql = """
                    #     SELECT min_amount, max_amount, daily_total_amount as daily_limit_amount, daily_order_count as daily_limit_count
                    #     FROM auto_payout_risk_config
                    #     WHERE id = 1
                    # """
                    # cur.execute(sql)
                    # account_limits = cur.fetchone()
                    #
                    # if not account_limits:
                    #     return {'passed': False, 'reason': 'risk_config_not_found'}

                    # ===== 新代码：查询payment表现有的限额字段（包括接单限额） =====
                    sql = """
                        SELECT amount_top, balance_limit
                        FROM payment
                        WHERE id = %s
                    """
                    cur.execute(sql, payment_id)
                    payment_info = cur.fetchone()

                    if not payment_info:
                        return {'passed': False, 'reason': 'payment_not_found'}

                    # ===== 旧代码：检查单笔金额限制 (已注释，payment表无对应字段) =====
                    # if amount < Decimal(str(account_limits.get('min_amount', 0))):
                    #     return {'passed': False, 'reason': 'amount_too_small'}
                    #
                    # if amount > Decimal(str(account_limits.get('max_amount', 999999))):
                    #     return {'passed': False, 'reason': 'amount_too_large'}

                    # ===== 单笔金额限制：payment表无对应字段，跳过检查 =====

                    # 检查今日额度限制
                    today_sql = """
                        SELECT COUNT(*) as today_count, COALESCE(SUM(amount), 0) as today_amount
                        FROM orders_df
                        WHERE payment_id = %s
                          AND DATE(time_create) = CURDATE()
                          AND status IN (3, 4)
                    """
                    cur.execute(today_sql, payment_id)
                    today_stats = cur.fetchone()

                    # ===== 旧代码：使用全局配置的限制 (已注释) =====
                    # daily_limit_count = account_limits.get('daily_limit_count', 999999)
                    # daily_limit_amount = account_limits.get('daily_limit_amount', 999999999)
                    #
                    # if today_stats['today_count'] >= daily_limit_count:
                    #     return {'passed': False, 'reason': 'daily_count_exceeded'}
                    #
                    # if Decimal(str(today_stats['today_amount'])) + amount > Decimal(str(daily_limit_amount)):
                    #     return {'passed': False, 'reason': 'daily_amount_exceeded'}

                    # ===== 新代码：使用payment表现有字段 (0或空不控制) =====
                    # 每日金额限制：使用 amount_top 字段
                    amount_top = payment_info.get('amount_top') or 0

                    # 每日金额限制：只有设置了大于0的值才检查
                    if amount_top and amount_top > 0:
                        if Decimal(str(today_stats['today_amount'])) + amount > Decimal(str(amount_top)):
                            return {'passed': False, 'reason': 'daily_amount_exceeded'}

                    # 接单限额检查：单笔最高金额限制
                    balance_limit = payment_info.get('balance_limit') or 0

                    # 如果 balance_limit 设置了大于0的值，检查订单金额是否超限
                    if balance_limit and balance_limit > 0:
                        if amount > Decimal(str(balance_limit)):
                            return {
                                'passed': False,
                                'reason': 'balance_limit_exceeded',
                                'amount': amount,
                                'balance_limit': balance_limit,
                                'message': f'订单金额{amount}超过接单限额{balance_limit}'
                            }

                    # 每日次数限制：payment表无对应字段，跳过检查

                    return {'passed': True}

            finally:
                connection.commit()

        except Exception as e:
            self.logger.error(f"检查账号payment_id:{payment_id}金额限制失败: {e}")
            return {'passed': True}  # 检查失败时放行


    def check_account_release_time(self, account_id: str) -> bool:
        """
        防护机制6: 检查账号释放时间
        参考callback.py中的payment_release_time机制
        """
        try:
            release_key = f"jazzcash_release:{account_id}"
            release_time_str = self.redis.hget(self.REDIS_KEYS['jazzcash_release_time'], release_key)

            if release_time_str:
                release_time = datetime.fromisoformat(release_time_str.decode())
                if datetime.now() < release_time:
                    self.logger.debug(f"账号{account_id}仍在释放期内，释放时间: {release_time}")
                    return False

            return True
        except Exception as e:
            self.logger.error(f"检查账号{account_id}释放时间失败: {e}")
            return True


    def set_account_release_time(self, account_id: str, release_seconds: int = None):
        """
        设置账号释放时间

        Args:
            account_id: 账号ID
            release_seconds: 释放时间（秒），如果为None则从配置读取
        """
        try:
            # 如果没有指定时间，从配置读取
            if release_seconds is None:
                try:
                    config_str = self.redis.get("easypaisa_paymentid_cooldown_seconds")
                    if config_str:
                        release_seconds = int(config_str.decode() if isinstance(config_str, bytes) else config_str)
                        self.logger.debug(f"账号释放时间使用配置: {release_seconds}秒")
                    else:
                        release_seconds = 300  # 默认5分钟
                        self.logger.debug(f"账号释放时间使用默认值: {release_seconds}秒")
                except Exception as e:
                    self.logger.error(f"读取冷却配置失败: {e}，使用默认值300秒")
                    release_seconds = 300

            release_key = f"jazzcash_release:{account_id}"
            release_time = datetime.now() + timedelta(seconds=release_seconds)
            self.redis.hset(
                self.REDIS_KEYS['jazzcash_release_time'],
                release_key,
                release_time.isoformat()
            )
            self.logger.debug(f"设置账号{account_id}释放时间: {release_time} ({release_seconds}秒)")
        except Exception as e:
            self.logger.error(f"设置账号{account_id}释放时间失败: {e}")

    # ========== 账号使用记录相关方法（支持动态冷却期） ==========


    def record_account_usage(self, payment_id: str):
        """记录账号使用，支持动态冷却期配置"""
        try:
            import time
            usage_key = f"{self.REDIS_KEYS['jazzcash_account_used_prefix']}{payment_id}"
            current_time = int(time.time())

            # 从Redis读取动态配置的冷却时间，如果没有配置则使用默认5分钟
            # 注意：与 EasyPaisa 共用此配置，admin 统一设置
            try:
                cooldown_seconds_str = self.redis.get("easypaisa_paymentid_cooldown_seconds")
                if cooldown_seconds_str:
                    cooldown_seconds = int(cooldown_seconds_str.decode() if isinstance(cooldown_seconds_str, bytes) else cooldown_seconds_str)
                    self.logger.info(f"使用动态冷却期配置: {cooldown_seconds}秒")
                else:
                    cooldown_seconds = 300  # 默认5分钟
                    self.logger.info(f"使用默认冷却期: {cooldown_seconds}秒")
            except Exception as config_e:
                cooldown_seconds = 300  # 读取配置失败时使用默认值
                self.logger.warning(f"读取冷却期配置失败，使用默认值300秒: {config_e}")

            # 设置动态冷却期
            self.redis.setex(usage_key, cooldown_seconds, current_time)
            cooldown_minutes = cooldown_seconds / 60
            self.logger.info(f"记录账号{payment_id}使用时间: {current_time}, 冷却期: {cooldown_minutes:.1f}分钟")

        except Exception as e:
            self.logger.error(f"记录账号{payment_id}使用失败: {e}")


    def is_account_recently_used(self, payment_id: str) -> bool:
        """检查账号是否在冷却期内使用过（支持动态配置）"""
        try:
            usage_key = f"{self.REDIS_KEYS['jazzcash_account_used_prefix']}{payment_id}"
            return self.redis.exists(usage_key)

        except Exception as e:
            self.logger.error(f"检查账号{payment_id}使用记录失败: {e}")
            return False  # 检查失败时假设未使用过


    def get_account_last_usage_time(self, payment_id: str) -> Optional[int]:
        """获取账号最后使用时间（可选，用于调试）"""
        try:
            usage_key = f"{self.REDIS_KEYS['jazzcash_account_used_prefix']}{payment_id}"
            usage_time_str = self.redis.get(usage_key)

            if usage_time_str:
                return int(usage_time_str.decode())
            return None

        except Exception as e:
            self.logger.error(f"获取账号{payment_id}使用时间失败: {e}")
            return None

    # ========== MySQL 余额相关方法 ==========

    def get_mysql_payout_candidates(self, min_balance: Decimal = Decimal('1000'), count: int = 50) -> List[Dict]:
        """从 MySQL payment.balance 获取 JazzCash 代付候选。"""
        try:
            connection = self._get_db_connection()
            try:
                with connection.cursor() as cur:
                    sql = """
                        SELECT id AS payment_id, phone, account, name, bank_type, bank_type_id,
                               partner_id, COALESCE(balance, 0) AS balance
                        FROM payment
                        WHERE {condition}
                          AND (bank_type = 98 OR bank_type_id = 98)
                          AND COALESCE(balance, 0) >= %s
                        ORDER BY balance DESC, id ASC
                        LIMIT %s
                    """.format(condition=payout_sql_condition("payment"))
                    cur.execute(sql, (min_balance, int(count)))
                    rows = cur.fetchall() or []
                    accounts = []
                    for row in rows:
                        balance = Decimal(str(row.get('balance') or 0))
                        accounts.append({
                            'payment_id': str(row.get('payment_id')),
                            'phone': row.get('phone'),
                            'partner_id': row.get('partner_id'),
                            'account': row.get('account'),
                            'name': row.get('name'),
                            'bank_type': row.get('bank_type'),
                            'balance': balance,
                            'priority': int(balance),
                        })
                    self.logger.info(f"从 MySQL payment.balance 获取 {len(accounts)} 个 JazzCash 代付候选")
                    return accounts
            finally:
                connection.commit()
        except Exception as e:
            self.logger.error(f"从 MySQL 获取 JazzCash 代付候选失败: {e}")
            return []

    def get_top_balance_accounts(self, min_balance: Decimal = Decimal('1000'), count: int = 50) -> List[Dict]:
        """从 MySQL payment.balance 获取余额最高的账号列表。"""
        return self.get_mysql_payout_candidates(min_balance=min_balance, count=count)

    def check_payment_balance(self, payment_id: str, transfer_amount: Decimal) -> bool:
        """抢单前复查 MySQL payment.balance，避免预分配后余额被并发消耗。"""
        connection = None
        try:
            connection = self._get_db_connection()
            with connection.cursor() as cur:
                affected = cur.execute(
                    """
                    SELECT id
                    FROM payment
                    WHERE id = %s
                      AND (bank_type = 98 OR bank_type_id = 98)
                      AND COALESCE(balance, 0) >= %s
                    LIMIT 1
                    """,
                    (payment_id, transfer_amount),
                )
            return affected == 1
        except Exception as e:
            self.logger.error(f"检查JazzCash账号{payment_id} MySQL余额失败: {e}")
            return False
        finally:
            if connection:
                try:
                    connection.commit()
                except Exception:
                    pass

    def deduct_account_balance_in_transaction(self, cur, payment_id: str, transfer_amount: Decimal) -> bool:
        """在订单成功结算同一事务内扣减 payment.balance。"""
        affected = cur.execute(
            """
            UPDATE payment
            SET balance = COALESCE(balance, 0) - %s,
                time_update = NOW()
            WHERE id = %s
              AND (bank_type = 98 OR bank_type_id = 98)
              AND COALESCE(balance, 0) >= %s
            LIMIT 1
            """,
            (transfer_amount, payment_id, transfer_amount),
        )
        self.logger.info(
            f"JazzCash账号{payment_id} 事务内扣减MySQL余额: -{transfer_amount}, affected={affected}"
        )
        return affected == 1


    async def get_available_accounts(self, amount: Decimal, target_account: str = None) -> List[Dict]:
        """
        账号获取：从 MySQL payment.balance 获取候选，加入20分钟使用间隔筛选。

        Args:
            amount: 转账金额
            target_account: 目标收款账号，用于过滤相同账号
        """
        available_accounts = []

        # 统计各种检查结果
        check_stats = {
            'mysql_candidate_attempts': 0,
            'total_attempted': 0,
            'offline_count': 0,
            'release_time_count': 0,
            'duplicate_failure_count': 0,
            'payment_id_locked_count': 0,
            'concurrent_orders_count': 0,
            'amount_limit_count': 0,
            'balance_limit_exceeded_count': 0,
            'same_account_count': 0,
            'insufficient_balance_count': 0,
            'no_balance_cache_count': 0,
            'recently_used_count': 0,
            'available_count': 0
        }

        try:
            self.logger.info(f"======== 开始JazzCash账号筛选（MySQL余额+使用间隔） ========")
            self.logger.info(f"筛选条件: 金额要求 >= {amount}")

            self.logger.info(f"从 MySQL payment.balance 获取高余额账号（余额>={amount}）")
            high_balance_accounts = self.get_top_balance_accounts(min_balance=amount, count=20)

            if high_balance_accounts:
                self.logger.info(f"从 MySQL 获取到 {len(high_balance_accounts)} 个高余额账号")

                # 对高余额账号进行防护检查（跳过余额检查）
                passed_accounts = []

                for account_info in high_balance_accounts:
                    payment_id = account_info['payment_id']
                    phone = account_info['phone']
                    balance = account_info['balance']

                    check_stats['mysql_candidate_attempts'] += 1
                    check_stats['total_attempted'] += 1

                    self.logger.info(f"检查高余额账号: payment_id:{payment_id} phone:{phone} 余额:{balance}")

                    # 🔥 新增：检查收付款账号是否相同
                    if target_account and phone == target_account:
                        self.logger.warning(f"账号{payment_id} - 付款账号与收款账号相同 [{phone}]，跳过")
                        check_stats['same_account_count'] = check_stats.get('same_account_count', 0) + 1
                        continue

                    # 检查1: 在线状态
                    if not await self.check_account_online_status(payment_id):
                        check_stats['offline_count'] += 1
                        self.logger.info(f"账号{payment_id} - 不在线，跳过")
                        continue

                    # 检查2: 释放时间
                    if not self.check_account_release_time(payment_id):
                        check_stats['release_time_count'] += 1
                        self.logger.info(f"账号{payment_id} - 在释放期内，跳过")
                        continue

                    # 🔥 检查3: 重复订单检测（直接查询Hash表）
                    self.logger.error(f"准备检查重复订单: payment_id={payment_id}, target_account={target_account}, amount={amount}")
                    if target_account:
                        # 有收款账号，执行精确的重复检测
                        duplicate_check = self.check_duplicate_failure(
                            payment_id=payment_id,
                            amount=amount,
                            to_account=target_account,
                            time_window=1200  # 20分钟
                        )

                        if duplicate_check['has_duplicate']:
                            # ❌ 检测到重复，跳过此账号
                            check_stats['duplicate_failure_count'] += 1
                            self.logger.error(
                                f"⚠️ 账号{payment_id}重复订单检测: "
                                f"20分钟内已失败{duplicate_check['duplicate_count']}次 "
                                f"(金额:{amount}, 收款:{target_account})，跳过"
                            )
                            continue
                        else:
                            # ✅ 没有重复，继续使用
                            self.logger.error(f"账号{payment_id}未检测到重复订单，继续使用")
                    else:
                        # 收款账号为空，无法做重复检测
                        self.logger.error(f"账号{payment_id}收款账号为空，跳过重复检测")

                    # 检查4: 并发订单 (已注释，由payment_id_lock机制处理)
                    # if not await self.check_account_concurrent_orders(payment_id):
                    #     check_stats['concurrent_orders_count'] += 1
                    #     self.logger.info(f"账号{payment_id} - 并发订单超限，跳过")
                    #     continue

                    # 新增：payment_id 锁检查（防止选中已被其他进程占用的账号）
                    lock_key = f'{self.REDIS_KEYS["payment_id_lock_prefix"]}{payment_id}'
                    if self.redis.exists(lock_key):
                        check_stats['payment_id_locked_count'] += 1
                        self.logger.info(f"账号{payment_id} - payment_id已被锁定，跳过")
                        continue

                    # 检查5: 金额限制和接单限额
                    amount_check = await self.check_account_amount_limits(payment_id, amount)
                    if not amount_check['passed']:
                        if amount_check['reason'] == 'balance_limit_exceeded':
                            check_stats['balance_limit_exceeded_count'] = check_stats.get('balance_limit_exceeded_count', 0) + 1
                            self.logger.info(f"账号{payment_id} - 接单限额检查: {amount_check['reason']}，跳过")
                        else:
                            check_stats['amount_limit_count'] += 1
                            self.logger.info(f"账号{payment_id} - 金额限制: {amount_check['reason']}，跳过")
                        continue

                    # 余额检查已通过（从 MySQL payment.balance 获取时已确保余额足够）
                    # 通过基础检查的账号
                    passed_accounts.append(account_info)
                    self.logger.info(f"✅ 账号{payment_id}通过基础检查")

                # 🔥 新增：20分钟使用间隔筛选
                if passed_accounts:
                    self.logger.info(f"开始20分钟使用间隔筛选，候选账号数: {len(passed_accounts)}")

                    # 筛选出20分钟内未使用的账号
                    unused_accounts = []
                    recently_used_accounts = []

                    for account_info in passed_accounts:
                        payment_id = account_info['payment_id']

                        if self.is_account_recently_used(payment_id):
                            # 获取使用时间用于日志
                            last_usage = self.get_account_last_usage_time(payment_id)
                            if last_usage:
                                import time
                                minutes_ago = (time.time() - last_usage) / 60
                                self.logger.info(f"账号{payment_id} - 在20分钟内使用过({minutes_ago:.1f}分钟前)，暂时排除")
                            else:
                                self.logger.info(f"账号{payment_id} - 在20分钟内使用过，暂时排除")
                            recently_used_accounts.append(account_info)
                            check_stats['recently_used_count'] += 1
                        else:
                            self.logger.info(f"账号{payment_id} - 20分钟内未使用，可优先选择")
                            unused_accounts.append(account_info)

                    # 🔥 关键逻辑：如果有未使用的账号，优先使用；否则使用最近使用的账号
                    if unused_accounts:
                        self.logger.info(f"✅ 选择20分钟内未使用的账号: {len(unused_accounts)}个可选")
                        available_accounts.append(unused_accounts[0])  # 选择第一个（余额最高的）
                        selected_account = unused_accounts[0]
                        check_stats['available_count'] += 1
                        self.logger.info(f"🎯 最终选择账号: payment_id={selected_account['payment_id']} phone={selected_account['phone']}, 余额={selected_account['balance']} (20分钟内未使用)")
                    else:
                        self.logger.warning(f"⚠️ 所有账号都在20分钟内使用过，选择最近使用的账号")
                        if recently_used_accounts:
                            available_accounts.append(recently_used_accounts[0])  # 选择第一个（余额最高的）
                            selected_account = recently_used_accounts[0]
                            check_stats['available_count'] += 1
                            self.logger.info(f"🎯 最终选择账号: payment_id={selected_account['payment_id']} phone={selected_account['phone']}, 余额={selected_account['balance']} (虽然20分钟内使用过，但无其他选择)")

            if not available_accounts:
                self.logger.info("MySQL 候选未筛出可用 JazzCash 代付账号，不再回退旧 Redis 队列")

            # 如果两个策略都未找到可用账号，记录详细原因
            if not available_accounts:
                self.logger.warning(f"❌ 两个策略都未找到可用账号")
                if not high_balance_accounts:
                    self.logger.error(f"🚨 MySQL 中无 payment.balance>={amount} 的 JazzCash 账号")
                else:
                    self.logger.error(f"🚨 MySQL 有{len(high_balance_accounts)}个高余额账号，但都不满足其他条件:")
                    self.logger.error(f"   - 离线账号: {check_stats['offline_count']}")
                    self.logger.error(f"   - 释放期账号: {check_stats['release_time_count']}")
                    self.logger.error(f"   - 重复失败账号: {check_stats['duplicate_failure_count']}")
                    self.logger.error(f"   - payment_id已锁定: {check_stats['payment_id_locked_count']}")
                    self.logger.error(f"   - 并发超限账号: {check_stats['concurrent_orders_count']}")
                    self.logger.error(f"   - 金额限制账号: {check_stats['amount_limit_count']}")
                    self.logger.error(f"   - 接单限额超限: {check_stats['balance_limit_exceeded_count']}")
                    self.logger.error(f"   - 收付款相同账号: {check_stats['same_account_count']}")
                    self.logger.error(f"   - 20分钟内使用过: {check_stats['recently_used_count']}")
                    self.logger.error(f"   - 余额不足账号: {check_stats['insufficient_balance_count']}")
                    self.logger.error(f"   - 无缓存账号: {check_stats['no_balance_cache_count']}")

            # 输出详细统计
            self.logger.info(f"======== JazzCash账号筛选完成 ========")
            self.logger.info(f"筛选统计:")
            self.logger.info(f"  📊 MySQL候选尝试: {check_stats['mysql_candidate_attempts']}")
            self.logger.info(f"  📊 总尝试账号数: {check_stats['total_attempted']}")
            self.logger.info(f"  ❌ 离线账号数: {check_stats['offline_count']}")
            self.logger.info(f"  ⏰ 释放期账号数: {check_stats['release_time_count']}")
            self.logger.info(f"  ⚠️ 重复失败账号数: {check_stats['duplicate_failure_count']}")
            self.logger.info(f"  🔒 payment_id已锁定数: {check_stats['payment_id_locked_count']}")
            self.logger.info(f"  🔄 并发超限账号数: {check_stats['concurrent_orders_count']}")
            self.logger.info(f"  💰 金额限制账号数: {check_stats['amount_limit_count']}")
            self.logger.info(f"  🚫 接单限额超限数: {check_stats['balance_limit_exceeded_count']}")
            self.logger.info(f"  🔁 收付款相同账号数: {check_stats['same_account_count']}")
            self.logger.info(f"  💸 余额不足账号数: {check_stats['insufficient_balance_count']}")
            self.logger.info(f"  💾 无缓存账号数: {check_stats['no_balance_cache_count']}")
            self.logger.info(f"  🕐 20分钟内使用过: {check_stats['recently_used_count']}")
            self.logger.info(f"  ✅ 可用账号数: {check_stats['available_count']}")

            if available_accounts:
                self.logger.info(f"🎯 筛选结果: 成功找到{len(available_accounts)}个可用账号")
            else:
                self.logger.info(f"⚠️ 筛选结果: 暂无可用账号")

            return available_accounts

        except Exception as e:
            self.logger.error(f"======== JazzCash账号筛选异常 ========")
            self.logger.error(f"异常详情: {e}")
            self.logger.error(f"异常时统计:")
            self.logger.error(f"  已检查账号数: {check_stats['total_attempted']}")
            self.logger.error(f"  MySQL候选尝试: {check_stats['mysql_candidate_attempts']}")

            self.logger.error(f"🚨 筛选结果: 因异常返回空列表")
            return []


    # ========== 原有的锁机制保持不变 ==========

    def get_lock(self, order_code):
        """获取订单锁（保持原有逻辑）"""
        try:
            busy_key = f'{self.REDIS_KEYS["grab_df_prefix"]}{order_code}'
            _value = secrets.token_hex(8)
            _lock = self.redis.setnx(busy_key, _value)
            if not _lock:
                _ttl = self.redis.ttl(busy_key)
                self.logger.info(f"{order_code}, {busy_key} 剩余生存时间 {_ttl} s")
                if _ttl and int(_ttl) > self.lock_time:
                    self.redis.delete(busy_key)
                    self.logger.error(f"{order_code}, 死锁并删除 {_value}")
                return False
            self.redis.expire(busy_key, self.lock_time)
            self.logger.info(f"{order_code},{busy_key} 加锁时间 {self.lock_time} s, _value: {_value}")
            return _value
        except Exception as e:
            self.logger.error(f'get_lock 脚本运行错误{order_code}\n{e}')
            return False


    def del_lock(self, order_code, value):
        """删除锁（保持原有逻辑）"""
        try:
            busy_key = f'{self.REDIS_KEYS["grab_df_prefix"]}{order_code}'
            self.logger.info(f"准备删除Lock {busy_key}, 期望value: {value}")
            _lock = self.redis.get(busy_key)
            if _lock:
                current_value = _lock.decode()
                if current_value == value:
                    result = self.redis.delete(busy_key)
                    self.logger.info(f"✅ 删除Lock成功 {busy_key}, result: {result}")
                else:
                    self.logger.warning(f"⚠️ Lock值不匹配！订单{order_code} 期望value: {value}, 实际value: {current_value}, 订单可能被其他进程处理")
            else:
                self.logger.warning(f"⚠️ Lock已不存在: {busy_key}, 订单{order_code}的锁可能提前过期或被清理")
            return True
        except Exception as e:
            self.logger.error(f'del_lock 脚本运行错误{order_code}\n{e}')
            return False


    def get_payment_id_lock(self, payment_id):
        """获取payment_id锁 - 确保每个payment_id只能处理一个订单"""
        try:
            # 🔥 防护：检查payment_id是否有效
            if payment_id is None or payment_id == '':
                self.logger.error(f"Payment ID 无效: {payment_id}，拒绝处理")
                return False

            # 🔥 注释：失败冷却期的精确检查已移到账号筛选阶段（get_available_accounts）
            # 在筛选阶段已经通过 check_duplicate_failure() 做了精确的重复订单检测
            # 如果账号能通过筛选到这里，说明：
            #   1. 不在冷却期，或者
            #   2. 虽在冷却期但不是重复订单（失败的是其他订单）
            # 因此这里不再重复检查，避免误判
            #
            # failed_key = f'{self.REDIS_KEYS["payment_id_failed_prefix"]}{payment_id}'
            # if self.redis.exists(failed_key):
            #     self.logger.warning(f"Payment ID {payment_id} 在冷却期内，拒绝处理")
            #     return False

            # 获取payment_id处理锁
            lock_key = f'{self.REDIS_KEYS["payment_id_lock_prefix"]}{payment_id}'
            _value = secrets.token_hex(8)
            _lock = self.redis.setnx(lock_key, _value)

            if not _lock:
                # 防止死锁
                _ttl = self.redis.ttl(lock_key)
                self.logger.info(f"Payment ID {payment_id} 锁剩余时间 {_ttl}s")
                if _ttl and int(_ttl) > 300:  # 5分钟超时
                    self.redis.delete(lock_key)
                    self.logger.error(f"Payment ID {payment_id} 死锁并删除")
                return False

            # 设置5分钟超时
            self.redis.expire(lock_key, 300)
            self.logger.info(f"Payment ID {payment_id} 获取锁成功，value: {_value}")
            return _value

        except Exception as e:
            self.logger.error(f'获取payment_id锁失败: {e}')
            return False


    def del_payment_id_lock(self, payment_id, value):
        """删除payment_id锁"""
        try:
            lock_key = f'{self.REDIS_KEYS["payment_id_lock_prefix"]}{payment_id}'
            _lock = self.redis.get(lock_key)
            if _lock and _lock.decode() == value:
                result = self.redis.delete(lock_key)
                self.logger.info(f"删除Payment ID锁 {lock_key}, result: {result}")
            return True
        except Exception as e:
            self.logger.error(f'删除payment_id锁失败: {e}')
            return False


    async def fetch_balance_from_api(self, account_info):
        """
        从API重新获取账号余额（参考easypaisa_monitor.py的实现）
        当Redis缓存不存在时调用此方法
        """
        import base64
        import hashlib
        import uuid
        import json
        import time

        try:
            payment_id = account_info['payment_id']
            phone = account_info.get('phone')

            # 检查必要信息
            if not phone:
                return {
                    'success': False,
                    'error': f'账号{payment_id}缺少手机号信息'
                }

            # 🔥 JazzCash 余额查询只需要 account_id（与 EasyPaisa 不同，不需要 account_accno）
            # 构造payload数据
            payload_data = {
                "account_id": phone  # 手机号
            }
            self.logger.info(f"payment_id {payment_id} JazzCash余额查询，account_id={phone}")

            # 构造内层payload（按照JazzCash文档格式）
            inner_payload = {
                "id": str(uuid.uuid4()),  # 生成UUID
                "action": "queryBalance",
                "payload": payload_data
            }

            secret_key = self.secret_key
            user_id = self.user_id
            api_url = self.api_url

            if not all([secret_key, user_id, api_url]):
                return {
                    'success': False,
                    'error': 'JazzCash API配置不完整'
                }

            form_data = build_form_body(
                inner_payload.get('action'),
                inner_payload.get('payload', {}),
                user_id,
                secret_key,
                request_id=inner_payload.get('id'),
            )

            self.logger.info(f"🔄 为账号{payment_id}({phone})重新获取余额")

            # 发起API请求
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}

            start_time = time.time()

            # 使用aiohttp发起异步请求
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url,
                    headers=headers,
                    data=form_data,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    response_time = time.time() - start_time

                    if not 200 <= response.status < 300:
                        return {
                            'success': False,
                            'error': f'HTTP错误: {response.status}',
                            'response_time': response_time
                        }

                    # 解析响应
                    result = await response.json()

                    if result.get('code') == 200:
                        # 🔥 根据JazzCash文档，余额在 data.data.avaliableBalance 字段
                        data = result.get('data', {})
                        inner_data = data.get('data', {}) if isinstance(data, dict) else {}
                        balance = inner_data.get('avaliableBalance', inner_data.get('availableBalance', 0))

                        self.logger.info(f"✅ 账号{payment_id}({phone})余额获取成功: {balance}")

                        return {
                            'success': True,
                            'balance': balance,
                            'response_time': response_time,
                            'data': result
                        }
                    elif result.get('code') == 501:
                        # 501 AccountInvalid - 账号无效
                        error_msg = result.get('msg', result.get('message', '账号无效(501)'))

                        return {
                            'success': False,
                            'error': error_msg,
                            'response_time': response_time,
                            'should_offline': True
                        }
                    else:
                        return {
                            'success': False,
                            'error': result.get('msg', result.get('message', 'API返回错误')),
                            'response_time': response_time
                        }

        except Exception as e:
            self.logger.error(f"重新获取账号{payment_id}余额异常: {e}")

            return {
                'success': False,
                'error': str(e),
                'response_time': 0
            }



    def record_payment_failure(self, payment_id: str, amount: Decimal,
                              to_account: str, reason: str, order_code: str):
        """
        记录失败信息到统一Hash

        Args:
            payment_id: 支付账号ID
            amount: 订单金额
            to_account: 收款账号
            reason: 失败原因
            order_code: 订单号

        Redis结构:
            Hash: jazzcash_failures
            Field: {payment_id}:{timestamp}
            Value: JSON包含失败详情
        """
        try:
            import time

            timestamp = int(time.time())
            field = f"{payment_id}:{timestamp}"

            failure_info = {
                'payment_id': payment_id,
                'amount': float(amount),
                'to_account': to_account,
                'reason': reason,
                'order_code': order_code,
                'timestamp': timestamp
            }

            # 存储到统一Hash
            self.redis.hset(
                self.REDIS_KEYS['jazzcash_failures'],
                field,
                json.dumps(failure_info, ensure_ascii=False)
            )

            self.logger.info(
                f"记录失败: payment_id={payment_id}, "
                f"金额={amount}, 收款账号={to_account}, 原因={reason}"
            )

        except Exception as e:
            self.logger.error(f"记录失败信息失败: {e}")


    def check_duplicate_failure(self, payment_id: str, amount: Decimal,
                                to_account: str, time_window: int = 1200) -> dict:
        """
        检查时间窗口内是否有相同金额和收款账号的失败

        Args:
            payment_id: 支付账号ID
            amount: 订单金额
            to_account: 收款账号
            time_window: 时间窗口（秒），默认1200=20分钟

        Returns:
            {
                'has_duplicate': bool,  # 是否有重复
                'duplicate_count': int,  # 重复次数
                'last_failure_time': int,  # 最后一次失败时间
                'failures': list  # 所有匹配的失败记录
            }
        """
        try:
            import time

            current_time = int(time.time())
            cutoff_time = current_time - time_window

            # 扫描该payment_id的所有失败记录
            pattern = f"{payment_id}:*"
            cursor = 0
            matching_failures = []
            expired_fields = []

            # 添加调试日志
            self.logger.debug(f"开始检查重复失败: payment_id={payment_id}, amount={amount}, to_account={to_account}, time_window={time_window}秒")

            while True:
                cursor, fields = self.redis.hscan(
                    self.REDIS_KEYS['jazzcash_failures'],
                    cursor,
                    match=pattern,
                    count=100
                )

                # 添加调试日志
                if fields:
                    self.logger.debug(f"扫描到{len(fields)}条记录，pattern={pattern}")

                for field, value in fields.items():
                    field_str = field.decode() if isinstance(field, bytes) else field

                    # 解析时间戳
                    parts = field_str.split(':')
                    if len(parts) >= 2:
                        try:
                            field_timestamp = int(parts[1])

                            # 检查是否过期
                            if field_timestamp < cutoff_time:
                                expired_fields.append(field)
                                continue

                            # 解析失败信息
                            value_str = value.decode() if isinstance(value, bytes) else value
                            failure_info = json.loads(value_str)

                            # 添加调试日志
                            self.logger.debug(f"检查记录: field={field_str}, amount={failure_info['amount']}, to_account={failure_info['to_account']}")

                            # 检查金额和收款账号是否匹配
                            amount_match = abs(failure_info['amount'] - float(amount)) < 0.01
                            account_match = failure_info['to_account'] == to_account

                            # 添加调试日志
                            self.logger.debug(f"匹配结果: amount_match={amount_match} ({failure_info['amount']} vs {amount}), account_match={account_match} ({failure_info['to_account']} vs {to_account})")

                            if amount_match and account_match:
                                matching_failures.append(failure_info)
                                self.logger.debug(f"找到匹配的失败记录！")

                        except (ValueError, json.JSONDecodeError) as e:
                            self.logger.error(f"解析失败记录错误: {field_str}, {e}")

                if cursor == 0:
                    break

            # 清理过期记录
            if expired_fields:
                self.redis.hdel(self.REDIS_KEYS['jazzcash_failures'], *expired_fields)
                self.logger.debug(f"清理{len(expired_fields)}条过期失败记录")

            return {
                'has_duplicate': len(matching_failures) > 0,
                'duplicate_count': len(matching_failures),
                'last_failure_time': max([f['timestamp'] for f in matching_failures]) if matching_failures else None,
                'failures': matching_failures
            }

        except Exception as e:
            self.logger.error(f"检查重复失败错误: {e}")
            return {
                'has_duplicate': False,
                'duplicate_count': 0,
                'last_failure_time': None,
                'failures': []
            }

    # ========== 订单冷却期管理机制 ==========


    def is_order_in_cooldown(self, order_code: str) -> bool:
        """检查订单是否在冷却期内"""
        try:
            # 直接使用 EasyPaisa 的订单冷却期Hash表（因为抢同一个订单表）
            hash_key = 'easypaisa_order_cooldown'
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
            # 直接使用 EasyPaisa 的订单冷却期Hash表（因为抢同一个订单表）
            hash_key = 'easypaisa_order_cooldown'
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
                'status': 'max_retry_final' if status == 3 else 'active',  # active=冷却中, max_retry_final=超限终结
                'order_amount': float(order_data.get('amount', 0)),
                'current_retry_count': order_data.get('retry_count', 0),
                'record_type': status  # 1=明确失败, 2=按成功处理, 3=超限异常按成功处理
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

        配置变更影响：
        - 已在冷却期的订单：不受影响（expire_time已固定）
        - 下一次失败的订单：使用新配置
        - 等级超出旧配置时：受新配置影响（如4级→6级，第5次失败会用新的等级5配置）
        """
        try:
            # 从 Redis 读取配置（使用EasyPaisa的配置，管理员统一设置）
            import json
            config_str = self.redis.get('easypaisa_order_cooldown_config')

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

                    # 🔥 关键：超过最大等级，使用最后一个配置（支持无限等级）
                    max_configured_level = max([lc['level'] for lc in levels_config])
                    if level > max_configured_level:
                        last_config = levels_config[-1]  # 获取最后一个配置
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

        # 🔥 默认值（向后兼容）- 使用统一逻辑
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

        # 超出默认配置范围，使用最后一个默认值（统一逻辑）
        last_default_minutes = default_levels[-1]['minutes']
        self.logger.info(f"[订单冷却期] 等级{level}超出默认范围，使用最后一级默认值: {last_default_minutes}分钟")
        return last_default_minutes


    def mark_order_cooldown_success(self, order_code: str):
        """标记订单成功处理，更新冷却记录状态"""
        try:
            import time
            # 直接使用 EasyPaisa 的订单冷却期Hash表（因为抢同一个订单表）
            hash_key = 'easypaisa_order_cooldown'
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



    def is_known_failure_reason(self, message: str) -> bool:
        """判断是否为明确的失败原因"""
        if not message:
            return False

        # API错误码（明确的失败原因，除了402都是明确失败）
        api_error_codes = [
            'code=401',  # SessionInvalid - 账号Session失效
            'code=403',  # CheckParam - 业务被拒绝，检查传入参数
            'code=423',  # ServerBusy - 云机正忙
            'code=500',  # Error - 服务器业务错误
            'code=501',  # AccountInvalid - 账号异常，可能锁号
            'code=503'   # NetworkError - 服务器网络问题
            # 注意：code=402不在此列表中，因为它按成功处理，不需要冷却期
        ]

        # 传统的失败原因模式
        known_patterns = [
            '余额不足', 'insufficient balance', 'low balance',
            '账号错误', 'invalid account', 'account not found',
            '账户被锁', 'account locked', 'account suspended',
            '超出限额', 'limit exceeded', 'amount limit',
            '账号异常', 'account error', 'account problem',
            '暂无可用账号', 'no available account', 'no account available',  # 系统资源问题
            '账号锁定失败', 'account lock failed', 'lock failed',           # 并发竞争问题
            '风控拦截', 'risk control', 'risk blocked'                      # 风控问题
        ]

        message_lower = message.lower()

        # 检查API错误码
        if any(code.lower() in message_lower for code in api_error_codes):
            return True

        # 检查传统失败原因
        return any(pattern.lower() in message_lower for pattern in known_patterns)


    def filter_cooldown_orders(self, orders: List[Dict]) -> List[Dict]:
        """批量过滤冷却期内的订单"""
        if not orders:
            return orders

        try:
            import time
            # 直接使用 EasyPaisa 的订单冷却期Hash表（因为抢同一个订单表）
            hash_key = 'easypaisa_order_cooldown'
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
                            # 这些记录仅用于统计，不影响订单处理
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


    async def acquire_account_lock(self, account_id: str, order_code: str) -> Optional[str]:
        """获取账号锁"""
        try:
            lock_key = f"{self.REDIS_KEYS['jazzcash_account_lock_prefix']}{account_id}"
            lock_value = f"{order_code}_{secrets.token_hex(8)}"

            if self.redis.setnx(lock_key, lock_value):
                self.redis.expire(lock_key, 300)  # 5分钟
                self.logger.info(f"账号{account_id}锁获取成功: {lock_value}")
                return lock_value
            else:
                self.logger.debug(f"账号{account_id}锁获取失败")
                return None

        except Exception as e:
            self.logger.error(f"获取账号{account_id}锁失败: {e}")
            return None


    def release_account_lock(self, account_id: str, lock_value: str):
        """释放账号锁"""
        try:
            lock_key = f"{self.REDIS_KEYS['jazzcash_account_lock_prefix']}{account_id}"
            current_value = self.redis.get(lock_key)
            if current_value and current_value.decode() == lock_value:
                self.redis.delete(lock_key)
                self.logger.info(f"账号{account_id}锁释放成功")
        except Exception as e:
            self.logger.error(f"释放账号{account_id}锁失败: {e}")

    # ========== 调度引擎 ==========
