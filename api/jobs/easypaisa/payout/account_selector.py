"""AccountSelector — account selection, limits, balance queries, and locks.

Extracted from auto_payout.py to reduce God Class complexity.
"""
import json
import time
import secrets
import hashlib
import base64
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Optional

import aiohttp

from jobs.common.db import DBConnection
from application.payment_eligibility import payout_sql_condition


class AccountSelector:
    """Handles account selection, limits, balance queries, and locks."""

    def __init__(self, redis_client, logger, conf: dict, REDIS_KEYS: dict,
                 api_url: str, user_id: str, secret_key: str,
                 db: DBConnection = None, db_provider=None):
        self.redis = redis_client
        self.logger = logger
        self.conf = conf
        self.REDIS_KEYS = REDIS_KEYS
        self.api_url = api_url
        self.user_id = user_id
        self.secret_key = secret_key
        self.db = db or DBConnection(conf)
        self.db_provider = db_provider
        self._invalid_payment_cache = {}
        # lock_time used by get_lock/del_lock (order lock)
        self.lock_time = 300

    def _get_db_connection(self):
        if callable(self.db_provider):
            return self.db_provider()
        return self.db.connection

    def _acquire_redis_lock(self, lock_key: str, lock_value: str, ttl: int) -> bool:
        return bool(self.redis.set(lock_key, lock_value, nx=True, ex=ttl))

    def _release_redis_lock(self, lock_key: str, lock_value: str) -> bool:
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        self.redis.eval(script, 1, lock_key, lock_value)
        return True

    # ========== Online Status ==========

    async def check_account_online_status(self, payment_id: str) -> bool:
        """
        防护机制1: 检查账号在线状态 - API优先，Redis同步
        现在使用 payment_id 作为参数，内部查询手机号调用 API
        """
        try:
            # 通过payment_id查询手机号
            payment_info = self.get_phone_by_payment_id(payment_id)
            if not payment_info or not payment_info.get('phone'):
                self.logger.warning(f"无法获取payment_id {payment_id} 的手机号信息，账号不可用")
                return False

            phone = payment_info['phone']
            self.logger.debug(f"payment_id {payment_id} 对应手机号: {phone}")

            # 策略1: 先通过API实时验证账号状态（使用手机号）
            api_result = await self._check_account_online_via_api(phone)

            if api_result is not None:
                if api_result:
                    self.logger.debug(f"账号payment_id:{payment_id} phone:{phone} API确认在线，MySQL payout_status 可派单")
                else:
                    self.logger.debug(f"账号payment_id:{payment_id} phone:{phone} API确认离线")

                return api_result
            else:
                self.logger.warning(f"账号payment_id:{payment_id} phone:{phone} API检查失败，按 MySQL payout_status 资格继续")
                return True

        except Exception as e:
            self.logger.error(f"检查账号payment_id:{payment_id}在线状态失败: {e}")
            return False

    async def _check_account_online_via_api(self, account_id: str) -> Optional[bool]:
        """
        通过EasyPaisa API实时检查账号在线状态

        Returns:
            True: 在线
            False: 离线
            None: API检查失败
        """
        try:
            # 构建isLogined请求
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
            response = await self._call_easypaisa_api_query(inner_payload, account_id)

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

    async def _call_easypaisa_api_query(self, inner_payload: dict, account_id: str) -> Optional[dict]:
        """Call EasyPaisa API with HMAC signing for query operations."""
        try:
            data_b64 = base64.b64encode(json.dumps(inner_payload).encode()).decode()
            sign_string = data_b64 + self.secret_key
            sign = hashlib.md5(sign_string.encode()).hexdigest()

            form_data = {
                'user_id': self.user_id,
                'data': data_b64,
                'sign': sign
            }

            headers = {'Content-Type': 'application/x-www-form-urlencoded'}

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url,
                    headers=headers,
                    data=form_data,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if 200 <= response.status < 300:
                        return await response.json()
                    else:
                        self.logger.warning(f"账号{account_id} API HTTP错误: {response.status}")
                        return None
        except Exception as e:
            self.logger.error(f"账号{account_id} API调用异常: {e}")
            return None

    # ========== Pakistan Mobile Number (CANONICAL) ==========

    def _is_pakistan_mobile_number(self, account_number: str) -> bool:
        """判断是否为巴基斯坦手机号（EasyPaisa账号格式）"""
        from jobs.easypaisa.payout.utils import is_pakistan_mobile_number
        return is_pakistan_mobile_number(account_number)

    # ========== Phone / Payment ID Lookup ==========

    def get_phone_by_payment_id(self, payment_id, connection=None):
        """通过payment_id查询手机号和相关信息"""
        start_time = time.time()

        try:
            if connection is None:
                connection = self._get_db_connection()

            try:
                with connection.cursor() as cur:
                    sql = """
                        SELECT phone, account, name, bank_type, bank_type_id, partner_id, wallet_status,
                               payout_status, status, certified, manual_status, account_accno
                        FROM payment
                        WHERE id = %s
                          AND {condition}
                    """
                    sql = sql.format(condition=payout_sql_condition("payment"))
                    cur.execute(sql, payment_id)
                    result = cur.fetchone()
                    query_time = time.time() - start_time

                    if result:
                        self.logger.info(f"[AutoPayout] payment_id={payment_id} 查询成功, 耗时: {query_time:.3f}s")
                        return result
                    else:
                        # 检查是否存在但状态不符合条件
                        check_sql = "SELECT wallet_status, payout_status, account_accno FROM payment WHERE id = %s"
                        cur.execute(check_sql, payment_id)
                        check_result = cur.fetchone()
                        if check_result:
                            self.logger.warning(f"[AutoPayout] payment_id={payment_id} 不可用: wallet_status={check_result['wallet_status']}, payout_status={check_result['payout_status']}, account_accno={check_result.get('account_accno')}, 耗时: {query_time:.3f}s")
                        else:
                            self.logger.warning(f"[AutoPayout] payment_id={payment_id} 不存在, 耗时: {query_time:.3f}s")
                        return None
            finally:
                connection.commit()

        except Exception as e:
            total_time = time.time() - start_time
            self.logger.error(f"[AutoPayout] 查询payment_id={payment_id} 失败: {e}, 耗时: {total_time:.3f}s")
            return None

    # ========== Amount Limits ==========

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

                    return {'passed': True}

            finally:
                connection.commit()

        except Exception as e:
            self.logger.error(f"检查账号payment_id:{payment_id}金额限制失败: {e}")
            return {'passed': True}  # 检查失败时放行

    # ========== Release Time ==========

    def check_account_release_time(self, account_id: str) -> bool:
        """
        防护机制6: 检查账号释放时间
        参考callback.py中的payment_release_time机制
        """
        try:
            release_key = f"easypaisa_release:{account_id}"
            release_time_str = self.redis.hget(self.REDIS_KEYS['easypaisa_release_time'], release_key)

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

            release_key = f"easypaisa_release:{account_id}"
            release_time = datetime.now() + timedelta(seconds=release_seconds)
            self.redis.hset(
                self.REDIS_KEYS['easypaisa_release_time'],
                release_key,
                release_time.isoformat()
            )
            self.logger.debug(f"设置账号{account_id}释放时间: {release_time} ({release_seconds}秒)")
        except Exception as e:
            self.logger.error(f"设置账号{account_id}释放时间失败: {e}")

    # ========== Failure Records ==========

    def record_payment_failure(self, payment_id: str, amount: Decimal,
                              to_account: str, reason: str, order_code: str):
        """
        记录失败信息到统一Hash

        Redis结构:
            Hash: easypaisa_failures
            Field: {payment_id}:{timestamp}
            Value: JSON包含失败详情
        """
        try:
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
                self.REDIS_KEYS['easypaisa_failures'],
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
        """
        try:
            current_time = int(time.time())
            cutoff_time = current_time - time_window

            # 扫描该payment_id的所有失败记录
            pattern = f"{payment_id}:*"
            cursor = 0
            matching_failures = []
            expired_fields = []

            # 添加调试日志
            self.logger.error(f"开始检查重复失败: payment_id={payment_id}, amount={amount}, to_account={to_account}, time_window={time_window}秒")

            while True:
                cursor, fields = self.redis.hscan(
                    self.REDIS_KEYS['easypaisa_failures'],
                    cursor,
                    match=pattern,
                    count=100
                )

                # 添加调试日志
                if fields:
                    self.logger.error(f"扫描到{len(fields)}条记录，pattern={pattern}")

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
                            self.logger.error(f"检查记录: field={field_str}, amount={failure_info['amount']}, to_account={failure_info['to_account']}")

                            # 检查金额和收款账号是否匹配
                            amount_match = abs(failure_info['amount'] - float(amount)) < 0.01
                            account_match = failure_info['to_account'] == to_account

                            # 添加调试日志
                            self.logger.error(f"匹配结果: amount_match={amount_match} ({failure_info['amount']} vs {amount}), account_match={account_match} ({failure_info['to_account']} vs {to_account})")

                            if amount_match and account_match:
                                matching_failures.append(failure_info)
                                self.logger.error(f"找到匹配的失败记录！")

                        except (ValueError, json.JSONDecodeError) as e:
                            self.logger.error(f"解析失败记录错误: {field_str}, {e}")

                if cursor == 0:
                    break

            # 清理过期记录
            if expired_fields:
                self.redis.hdel(self.REDIS_KEYS['easypaisa_failures'], *expired_fields)
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

    # ========== Account Usage Records (Dynamic Cooldown) ==========

    def record_account_usage(self, payment_id: str):
        """记录账号使用，支持动态冷却期配置"""
        try:
            usage_key = f"{self.REDIS_KEYS['easypaisa_account_used_prefix']}{payment_id}"
            current_time = int(time.time())

            # 从Redis读取动态配置的冷却时间，如果没有配置则使用默认5分钟
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
            usage_key = f"{self.REDIS_KEYS['easypaisa_account_used_prefix']}{payment_id}"
            return self.redis.exists(usage_key)

        except Exception as e:
            self.logger.error(f"检查账号{payment_id}使用记录失败: {e}")
            return False  # 检查失败时假设未使用过

    def get_account_last_usage_time(self, payment_id: str) -> Optional[int]:
        """获取账号最后使用时间（可选，用于调试）"""
        try:
            usage_key = f"{self.REDIS_KEYS['easypaisa_account_used_prefix']}{payment_id}"
            usage_time_str = self.redis.get(usage_key)

            if usage_time_str:
                return int(usage_time_str.decode())
            return None

        except Exception as e:
            self.logger.error(f"获取账号{payment_id}使用时间失败: {e}")
            return None
    # ========== Balance from MySQL ==========

    def get_mysql_payout_candidates(self, min_balance: Decimal = Decimal('1000'), count: int = 50, connection=None) -> List[Dict]:
        """从 MySQL 余额真相源获取 EasyPaisa 代付候选。"""
        connection = connection or self._get_db_connection()
        try:
            with connection.cursor() as cur:
                sql = """
                    SELECT id AS payment_id, phone, account, name, bank_type, bank_type_id,
                           partner_id, account_accno, COALESCE(balance, 0) AS balance,
                           COALESCE(amount_top, 0) AS amount_top,
                           COALESCE(balance_limit, 0) AS balance_limit,
                           COALESCE(today.today_amount, 0) AS today_amount
                    FROM payment
                    LEFT JOIN (
                        SELECT payment_id, COALESCE(SUM(amount), 0) AS today_amount
                        FROM orders_df
                        WHERE DATE(time_create) = CURDATE()
                          AND status IN (1, 3, 4)
                        GROUP BY payment_id
                    ) today ON today.payment_id = payment.id
                    WHERE {condition}
                      AND (bank_type = 97 OR bank_type_id = 97)
                      AND COALESCE(balance, 0) >= %s
                    ORDER BY balance DESC, id ASC
                    LIMIT %s
                """.format(condition=payout_sql_condition("payment"))
                cur.execute(sql, (min_balance, int(count)))
                rows = cur.fetchall() or []

            accounts = []
            for row in rows:
                balance = Decimal(str(row.get('balance') or 0))
                amount_top = Decimal(str(row.get('amount_top') or 0))
                today_amount = Decimal(str(row.get('today_amount') or 0))
                daily_remaining = amount_top - today_amount if amount_top > 0 else None
                accounts.append({
                    'payment_id': str(row.get('payment_id')),
                    'phone': row.get('phone'),
                    'partner_id': row.get('partner_id'),
                    'account': row.get('account'),
                    'name': row.get('name'),
                    'account_accno': row.get('account_accno'),
                    'balance': balance,
                    'amount_top': amount_top,
                    'balance_limit': Decimal(str(row.get('balance_limit') or 0)),
                    'today_amount': today_amount,
                    'daily_remaining': daily_remaining,
                    'priority': int(balance),
                })
            self.logger.info(f"从 MySQL payment.balance 获取 {len(accounts)} 个 EasyPaisa 代付候选")
            return accounts
        except Exception as e:
            self.logger.error(f"从 MySQL 获取 EasyPaisa 代付候选失败: {e}")
            return []
        finally:
            if connection:
                connection.commit()

    def get_top_balance_accounts(self, min_balance: Decimal = Decimal('1000'), count: int = 50, connection=None) -> List[Dict]:
        """从 MySQL payment.balance 获取余额最高的账号列表。"""
        return self.get_mysql_payout_candidates(min_balance=min_balance, count=count, connection=connection)

    # ========== Balance Update & API Fetch ==========

    def check_payment_balance(self, payment_id: str, amount: Decimal) -> bool:
        """锁内复查 MySQL 当前余额，避免多 worker 使用预选旧余额。"""
        connection = None
        try:
            connection = self._get_db_connection()
            with connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT COALESCE(balance, 0) AS balance
                    FROM payment
                    WHERE id = %s
                      AND (bank_type = 97 OR bank_type_id = 97)
                    LIMIT 1
                    """,
                    (payment_id,),
                )
                row = cur.fetchone()
            if connection:
                connection.commit()
            if not row:
                return False
            return Decimal(str(row.get('balance') or 0)) >= Decimal(str(amount))
        except Exception as e:
            if connection:
                try:
                    connection.rollback()
                except Exception:
                    pass
            self.logger.error(f"检查账号{payment_id} MySQL余额失败: {e}")
            return False

    def deduct_account_balance_in_transaction(self, cur, payment_id: str, transfer_amount: Decimal) -> bool:
        """在订单成功结算同一事务内扣减 payment.balance。"""
        affected = cur.execute(
            """
            UPDATE payment
            SET balance = COALESCE(balance, 0) - %s,
                time_update = NOW()
            WHERE id = %s
              AND (bank_type = 97 OR bank_type_id = 97)
              AND COALESCE(balance, 0) >= %s
            LIMIT 1
            """,
            (transfer_amount, payment_id, transfer_amount),
        )
        self.logger.info(
            f"EasyPaisa账号{payment_id} 事务内扣减MySQL余额: -{transfer_amount}, affected={affected}"
        )
        return affected == 1

    def update_account_balance_after_transfer(self, payment_id: str, transfer_amount: Decimal):
        """
        转账成功后扣减 MySQL payment.balance，避免代付选号依赖旧 Redis 余额。

        Args:
            payment_id: 账号ID
            transfer_amount: 转账金额（正数）

        Returns:
            bool: 更新成功返回True，失败返回False
        """
        connection = None
        try:
            connection = self._get_db_connection()
            with connection.cursor() as cur:
                affected = cur.execute(
                    """
                    UPDATE payment
                    SET balance = COALESCE(balance, 0) - %s,
                        time_update = NOW()
                    WHERE id = %s
                      AND (bank_type = 97 OR bank_type_id = 97)
                      AND COALESCE(balance, 0) >= %s
                    LIMIT 1
                    """,
                    (transfer_amount, payment_id, transfer_amount),
                )
                connection.commit()
            self.logger.info(f"EasyPaisa账号{payment_id} MySQL余额已扣减: -{transfer_amount}, affected={affected}")
            return affected > 0

        except Exception as e:
            if connection:
                try:
                    connection.rollback()
                except Exception:
                    pass
            self.logger.error(f"更新账号{payment_id}余额失败: {e}")
            import traceback
            self.logger.error(f"异常堆栈: {traceback.format_exc()}")
            return False

    async def fetch_balance_from_api(self, account_info):
        """
        从API重新获取账号余额（参考easypaisa_monitor.py的实现）
        当Redis缓存不存在时调用此方法
        """
        try:
            payment_id = account_info['payment_id']
            phone = account_info.get('phone')

            # 检查必要信息
            if not phone:
                return {
                    'success': False,
                    'error': f'账号{payment_id}缺少手机号信息'
                }

            # account_accno为余额查询必送参数
            account_accno = account_info.get('account_accno')
            if not account_accno:
                return {
                    'success': False,
                    'error': f'账号{payment_id}缺少account_accno字段，无法查询余额'
                }

            # 构造payload数据
            payload_data = {
                "account_id": phone,  # 手机号
                "accno": account_accno  # 必送的账号参数
            }
            self.logger.info(f"payment_id {payment_id} 余额查询，account_id={phone}, accno={account_accno}")

            # 构造内层payload（按照EasyPaisa文档格式）
            inner_payload = {
                "id": str(uuid.uuid4()),  # 生成UUID
                "action": "queryBalance",
                "payload": payload_data
            }

            # 构造FormBody格式（按照EasyPaisa文档）- 安全序列化
            try:
                data_b64 = base64.b64encode(json.dumps(inner_payload).encode()).decode()
            except TypeError as e:
                # 如果有Decimal类型导致序列化失败，使用安全转换
                self.logger.warning(f"余额查询JSON序列化失败，使用安全转换: {e}")

                def safe_convert(obj):
                    if isinstance(obj, Decimal):
                        return float(obj)
                    elif isinstance(obj, dict):
                        return {k: safe_convert(v) for k, v in obj.items()}
                    elif isinstance(obj, (list, tuple)):
                        return [safe_convert(item) for item in obj]
                    else:
                        return obj

                safe_payload = safe_convert(inner_payload)
                data_b64 = base64.b64encode(json.dumps(safe_payload).encode()).decode()

            # 计算MD5签名（使用注入的配置）
            if not all([self.secret_key, self.user_id, self.api_url]):
                return {
                    'success': False,
                    'error': 'EasyPaisa API配置不完整'
                }

            sign_string = data_b64 + self.secret_key
            sign = hashlib.md5(sign_string.encode()).hexdigest()

            form_data = {
                'user_id': self.user_id,
                'data': data_b64,
                'sign': sign
            }

            self.logger.info(f"为账号{payment_id}({phone})重新获取余额")

            # 发起API请求
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}

            start_time = time.time()

            # 使用aiohttp发起异步请求
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url,
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
                        # 根据EasyPaisa文档，余额在 data.body.totalbalance 字段
                        data = result.get('data', {})
                        body = data.get('body', {}) if isinstance(data, dict) else {}
                        balance = body.get('totalbalance', result.get('totalbalance', result.get('balance', 0)))

                        self.logger.info(f"账号{payment_id}({phone})余额获取成功: {balance}")

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
    # ========== Locks ==========

    async def acquire_account_lock(self, account_id: str, order_code: str) -> Optional[str]:
        """获取账号锁"""
        try:
            lock_key = f"{self.REDIS_KEYS['easypaisa_account_lock_prefix']}{account_id}"
            lock_value = f"{order_code}_{secrets.token_hex(8)}"

            if self._acquire_redis_lock(lock_key, lock_value, 300):
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
            lock_key = f"{self.REDIS_KEYS['easypaisa_account_lock_prefix']}{account_id}"
            self._release_redis_lock(lock_key, lock_value)
            self.logger.info(f"账号{account_id}锁释放成功")
        except Exception as e:
            self.logger.error(f"释放账号{account_id}锁失败: {e}")

    def get_payment_id_lock(self, payment_id):
        """获取payment_id锁 - 确保每个payment_id只能处理一个订单"""
        try:
            # 防护：检查payment_id是否有效
            if payment_id is None or payment_id == '':
                self.logger.error(f"Payment ID 无效: {payment_id}，拒绝处理")
                return False

            # 获取payment_id处理锁
            lock_key = f'{self.REDIS_KEYS["payment_id_lock_prefix"]}{payment_id}'
            _value = secrets.token_hex(8)
            _lock = self._acquire_redis_lock(lock_key, _value, 300)

            if not _lock:
                _ttl = self.redis.ttl(lock_key)
                self.logger.info(f"Payment ID {payment_id} 锁剩余时间 {_ttl}s")
                if _ttl == -1:
                    self.logger.error(f"Payment ID {payment_id} 锁缺少TTL，需要人工清理")
                return False

            self.logger.info(f"Payment ID {payment_id} 获取锁成功，value: {_value}")
            return _value

        except Exception as e:
            self.logger.error(f'获取payment_id锁失败: {e}')
            return False

    def del_payment_id_lock(self, payment_id, value):
        """删除payment_id锁"""
        try:
            lock_key = f'{self.REDIS_KEYS["payment_id_lock_prefix"]}{payment_id}'
            self._release_redis_lock(lock_key, value)
            self.logger.info(f"删除Payment ID锁 {lock_key}")
            return True
        except Exception as e:
            self.logger.error(f'删除payment_id锁失败: {e}')
            return False

    def get_lock(self, order_code):
        """获取订单锁（保持原有逻辑）"""
        try:
            busy_key = f'{self.REDIS_KEYS["grab_df_prefix"]}{order_code}'
            _value = secrets.token_hex(8)
            _lock = self._acquire_redis_lock(busy_key, _value, self.lock_time)
            if not _lock:
                _ttl = self.redis.ttl(busy_key)
                self.logger.info(f"{order_code}, {busy_key} 剩余生存时间 {_ttl} s")
                if _ttl == -1:
                    self.logger.error(f"{order_code}, {busy_key} 锁缺少TTL，需要人工清理")
                return False
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
            self._release_redis_lock(busy_key, value)
            self.logger.info(f"删除Lock完成 {busy_key}")
            return True
        except Exception as e:
            self.logger.error(f'del_lock 脚本运行错误{order_code}\n{e}')
            return False
    # ========== Batch Dispatch ==========

    async def get_real_available_accounts(self, orders: List[Dict]) -> List[Dict]:
        """
        获取当前真正可用的账号列表，供预分配调度使用。
        包含所有防护检查：在线、释放时间、锁、金额限制、使用间隔。
        """
        if not orders:
            return []

        min_amount = min(Decimal(str(o['amount'])) for o in orders)
        self.logger.info(f"预分配：获取可用账号，最小订单金额={min_amount}")

        raw_accounts = self.get_top_balance_accounts(min_balance=min_amount, count=50)
        if not raw_accounts:
            self.logger.warning("预分配：无余额满足要求的账号")
            return []

        available = []
        skip_stats = {'offline': 0, 'release': 0, 'locked': 0, 'amount_limit': 0, 'recently_used': 0}

        for account in raw_accounts:
            pid = account['payment_id']

            if not await self.check_account_online_status(pid):
                skip_stats['offline'] += 1
                continue

            if not self.check_account_release_time(pid):
                skip_stats['release'] += 1
                continue

            lock_key = f'{self.REDIS_KEYS["payment_id_lock_prefix"]}{pid}'
            if self.redis.exists(lock_key):
                skip_stats['locked'] += 1
                continue

            amount_check = await self.check_account_amount_limits(pid, min_amount)
            if not amount_check.get('passed', True):
                skip_stats['amount_limit'] += 1
                continue

            if self.is_account_recently_used(pid):
                skip_stats['recently_used'] += 1
                continue

            available.append(account)

        self.logger.info(
            f"预分配：从{len(raw_accounts)}个候选中筛出{len(available)}个可用账号 "
            f"(离线:{skip_stats['offline']}, 释放期:{skip_stats['release']}, "
            f"已锁:{skip_stats['locked']}, 限额:{skip_stats['amount_limit']}, "
            f"近期使用:{skip_stats['recently_used']})"
        )
        return available

    def dispatch_orders_to_accounts(self, orders: List[Dict], accounts: List[Dict]) -> List[tuple]:
        """
        按金额降序 + 虚拟余额扣减分配订单到账号。
        Returns: List[(account_dict, [order_dict, ...])]
        """
        if not accounts or not orders:
            return []

        orders_sorted = sorted(orders, key=lambda o: Decimal(str(o['amount'])), reverse=True)
        accounts_sorted = sorted(accounts, key=lambda a: a.get('balance', 0), reverse=True)
        virtual_balances = {a['payment_id']: Decimal(str(a.get('balance', 0))) for a in accounts_sorted}
        virtual_daily_remaining = {}
        for account in accounts_sorted:
            pid = account['payment_id']
            amount_top = Decimal(str(account.get('amount_top') or 0))
            if account.get('daily_remaining') is not None:
                virtual_daily_remaining[pid] = Decimal(str(account.get('daily_remaining') or 0))
            else:
                virtual_daily_remaining[pid] = amount_top if amount_top > 0 else None
        buckets = {a['payment_id']: {'account': a, 'orders': []} for a in accounts_sorted}
        assigned_pids = set()
        unassigned = []

        for order in orders_sorted:
            amount = Decimal(str(order['amount']))
            best_pid = None
            best_remaining = Decimal('-1')
            for a in accounts_sorted:
                pid = a['payment_id']
                if pid in assigned_pids:
                    continue
                balance_limit = Decimal(str(a.get('balance_limit') or 0))
                if balance_limit > 0 and amount > balance_limit:
                    continue
                daily_remaining = virtual_daily_remaining.get(pid)
                if daily_remaining is not None and amount > daily_remaining:
                    continue
                remaining = virtual_balances[pid]
                if remaining >= amount and remaining > best_remaining:
                    best_pid = pid
                    best_remaining = remaining
            if best_pid:
                buckets[best_pid]['orders'].append(order)
                virtual_balances[best_pid] -= amount
                if virtual_daily_remaining[best_pid] is not None:
                    virtual_daily_remaining[best_pid] -= amount
                assigned_pids.add(best_pid)
            else:
                unassigned.append(order)

        if unassigned:
            self.logger.info(f"预分配：{len(unassigned)}个订单因余额不足未分配，留给下轮")

        result = [(v['account'], v['orders']) for v in buckets.values() if v['orders']]

        for account, assigned_orders in result:
            self.logger.info(
                f"预分配：账号{account['payment_id']}"
                f"(余额{account.get('balance','?')}→虚拟剩余{virtual_balances[account['payment_id']]}) "
                f"分配{len(assigned_orders)}个订单"
            )

        return result
