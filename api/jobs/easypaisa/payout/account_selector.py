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

import pymysql
import aiohttp

from application.payment_eligibility import payout_sql_condition


class AccountSelector:
    """Handles account selection, limits, balance queries, and locks."""

    def __init__(self, redis_client, logger, conf: dict, REDIS_KEYS: dict,
                 api_url: str, user_id: str, secret_key: str):
        self.redis = redis_client
        self.logger = logger
        self.conf = conf
        self.REDIS_KEYS = REDIS_KEYS
        self.api_url = api_url
        self.user_id = user_id
        self.secret_key = secret_key
        self._invalid_payment_cache = {}
        # lock_time used by get_lock/del_lock (order lock)
        self.lock_time = 300

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

        own_connection = False
        try:
            if connection is None:
                own_connection = True
                connection = pymysql.connect(
                    host=self.conf['mysql_host'],
                    user=self.conf['mysql_user'],
                    password=self.conf['mysql_password'],
                    db=self.conf['mysql_database'],
                    charset='utf8mb4',
                    cursorclass=pymysql.cursors.DictCursor
                )

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
                if own_connection:
                    connection.close()

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
            connection = pymysql.connect(
                host=self.conf['mysql_host'],
                user=self.conf['mysql_user'],
                password=self.conf['mysql_password'],
                db=self.conf['mysql_database'],
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )

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
                connection.close()

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
    # ========== Balance from Sorted Set ==========

    def get_mysql_payout_candidates(self, min_balance: Decimal = Decimal('1000'), count: int = 50, connection=None) -> List[Dict]:
        """Redis 余额缓存丢失时，从 MySQL 资格源恢复代付候选。"""
        own_conn = False
        try:
            if connection is None:
                own_conn = True
                connection = pymysql.connect(
                    host=self.conf['mysql_host'],
                    user=self.conf['mysql_user'],
                    password=self.conf['mysql_password'],
                    db=self.conf['mysql_database'],
                    charset='utf8mb4',
                    cursorclass=pymysql.cursors.DictCursor,
                )

            with connection.cursor() as cur:
                sql = """
                    SELECT id AS payment_id, phone, account, name, bank_type, bank_type_id,
                           partner_id, account_accno, COALESCE(balance, 0) AS balance
                    FROM payment
                    WHERE {condition}
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
                    'account_accno': row.get('account_accno'),
                    'balance': balance,
                    'priority': int(balance),
                })
            self.logger.info(f"从 MySQL eligibility 获取 {len(accounts)} 个代付候选")
            return accounts
        except Exception as e:
            self.logger.error(f"从 MySQL 获取 EasyPaisa 代付候选失败: {e}")
            return []
        finally:
            if own_conn and connection:
                connection.close()

    def get_top_balance_accounts(self, min_balance: Decimal = Decimal('1000'), count: int = 50, connection=None) -> List[Dict]:
        """从有序集合获取余额最高的账号列表，带幽灵缓存过滤"""
        try:
            balance_sorted_set = self.REDIS_KEYS['easypaisa_balance_sorted_set']

            if not self.redis.exists(balance_sorted_set):
                self.logger.warning(f"有序集合 {balance_sorted_set} 不存在")
                return self.get_mysql_payout_candidates(min_balance=min_balance, count=count, connection=connection)

            # 多取一些补偿幽灵账号
            fetch_count = count * 2
            accounts_with_balance = self.redis.zrevrangebyscore(
                balance_sorted_set, "+inf", float(min_balance),
                start=0, num=fetch_count, withscores=True
            )

            if not accounts_with_balance:
                self.logger.info(f"有序集合中无余额>={min_balance}的账号")
                return self.get_mysql_payout_candidates(min_balance=min_balance, count=count, connection=connection)

            # 清理过期缓存
            now = time.time()
            expired = [k for k, v in self._invalid_payment_cache.items() if v < now]
            for k in expired:
                del self._invalid_payment_cache[k]

            # 过滤幽灵缓存
            filtered = []
            cached_skip = 0
            for payment_id_bytes, balance in accounts_with_balance:
                pid = payment_id_bytes.decode() if isinstance(payment_id_bytes, bytes) else str(payment_id_bytes)
                if pid in self._invalid_payment_cache:
                    cached_skip += 1
                    continue
                filtered.append((pid, balance))
                if len(filtered) >= count:
                    break

            if cached_skip > 0:
                self.logger.info(f"幽灵缓存过滤: 跳过{cached_skip}个已知无效账号")

            # 创建或复用 MySQL 连接验证账号
            own_conn = False
            if connection is None:
                own_conn = True
                connection = pymysql.connect(
                    host=self.conf['mysql_host'], user=self.conf['mysql_user'],
                    password=self.conf['mysql_password'], db=self.conf['mysql_database'],
                    charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
                )

            try:
                result_accounts = []
                invalid_count = 0

                for pid, balance in filtered:
                    payment_info = self.get_phone_by_payment_id(pid, connection=connection)
                    if payment_info and payment_info.get('phone'):
                        result_accounts.append({
                            'payment_id': pid,
                            'phone': payment_info['phone'],
                            'partner_id': payment_info.get('partner_id'),
                            'account': payment_info.get('account'),
                            'name': payment_info.get('name'),
                            'account_accno': payment_info.get('account_accno'),
                            'balance': Decimal(str(balance)),
                            'priority': int(balance)
                        })
                    else:
                        # 加入幽灵缓存，5分钟后重试
                        self._invalid_payment_cache[pid] = time.time() + 300
                        invalid_count += 1

                self.logger.info(f"从有序集合获取 {len(result_accounts)} 个有效账号（检查{len(filtered)}个，无效{invalid_count}个，缓存跳过{cached_skip}个）")
                return result_accounts
            finally:
                if own_conn:
                    connection.close()

        except Exception as e:
            self.logger.error(f"从有序集合获取高余额账号失败: {e}")
            return []

    def get_account_balance_from_sorted_set(self, payment_id: str) -> Optional[Decimal]:
        """从有序集合获取账号余额"""
        try:
            balance_sorted_set = self.REDIS_KEYS['easypaisa_balance_sorted_set']
            balance = self.redis.zscore(balance_sorted_set, payment_id)
            return Decimal(str(balance)) if balance is not None else None
        except Exception as e:
            self.logger.error(f"从有序集合获取账号{payment_id}余额失败: {e}")
            return None
    # ========== Balance Update & API Fetch ==========

    def update_account_balance_after_transfer(self, payment_id: str, transfer_amount: Decimal):
        """
        转账成功后更新Redis中的账号余额（仅扣减金额）

        Args:
            payment_id: 账号ID
            transfer_amount: 转账金额（正数）

        Returns:
            bool: 更新成功返回True，失败返回False
        """
        try:
            # 1. 更新有序集合中的余额（使用 ZINCRBY 原子操作扣减）
            balance_sorted_set = self.REDIS_KEYS['easypaisa_balance_sorted_set']
            new_balance = self.redis.zincrby(balance_sorted_set, -float(transfer_amount), payment_id)

            # 如果余额变为负数，设置为0（但不移除）
            if new_balance is not None and float(new_balance) < 0:
                self.redis.zadd(balance_sorted_set, {payment_id: 0})
                self.logger.info(f"账号{payment_id}余额扣减后为负({new_balance})，已设置为0")
                new_balance = 0

            # 2. 更新普通缓存的余额（不设置过期时间，由monitor负责）
            balance_key = f"{self.REDIS_KEYS['easypaisa_balance_prefix']}{payment_id}"
            cached_balance = self.redis.get(balance_key)

            if cached_balance:
                old_balance = Decimal(cached_balance.decode())
                new_balance_value = old_balance - transfer_amount
                # 如果扣减后为负数，设置为0
                if new_balance_value < 0:
                    new_balance_value = Decimal('0')
                # 直接SET，不设置过期时间
                self.redis.set(balance_key, str(new_balance_value))
                self.logger.info(f"账号{payment_id}余额已扣减: -{transfer_amount}, 新余额: {new_balance_value}")
            else:
                self.logger.info(f"账号{payment_id}普通缓存无余额记录，仅更新有序集合")

            return True

        except Exception as e:
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
            lock_key = f"{self.REDIS_KEYS['easypaisa_account_lock_prefix']}{account_id}"
            current_value = self.redis.get(lock_key)
            if current_value and current_value.decode() == lock_value:
                self.redis.delete(lock_key)
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
                    self.logger.info(f"删除Lock成功 {busy_key}, result: {result}")
                else:
                    self.logger.warning(f"Lock值不匹配！订单{order_code} 期望value: {value}, 实际value: {current_value}, 订单可能被其他进程处理")
            else:
                self.logger.warning(f"Lock已不存在: {busy_key}, 订单{order_code}的锁可能提前过期或被清理")
            return True
        except Exception as e:
            self.logger.error(f'del_lock 脚本运行错误{order_code}\n{e}')
            return False
    # ========== Main Account Selection ==========

    async def get_available_accounts(self, amount: Decimal, target_account: str = None) -> List[Dict]:
        """
        账号获取：MySQL payout_status 资格 + 余额排序方案，加入20分钟使用间隔筛选

        优先从有序集合获取高余额账号；有序集合为空时 get_top_balance_accounts 内部回退 MySQL。
        不再消费旧 Redis 队列。
        """
        available_accounts = []

        # 统计各种检查结果
        check_stats = {
            'sorted_set_attempts': 0,
            'active_list_attempts': 0,
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
            self.logger.info(f"======== 开始EasyPaisa账号筛选（双策略+使用间隔） ========")
            self.logger.info(f"筛选条件: 金额要求 >= {amount}")

            # 策略1: 优先从有序集合获取高余额账号
            self.logger.info(f"策略1: 从有序集合获取高余额账号（余额>={amount}）")
            high_balance_accounts = self.get_top_balance_accounts(min_balance=amount, count=20)

            if high_balance_accounts:
                self.logger.info(f"从有序集合获取到 {len(high_balance_accounts)} 个高余额账号")

                # 对高余额账号进行防护检查（跳过余额检查）
                passed_accounts = []

                for account_info in high_balance_accounts:
                    payment_id = account_info['payment_id']
                    phone = account_info['phone']
                    balance = account_info['balance']

                    check_stats['sorted_set_attempts'] += 1
                    check_stats['total_attempted'] += 1

                    self.logger.debug(f"检查高余额账号: payment_id:{payment_id} phone:{phone} 余额:{balance}")

                    # 检查收付款账号是否相同
                    if target_account and phone == target_account:
                        self.logger.warning(f"账号{payment_id} - 付款账号与收款账号相同 [{phone}]，跳过")
                        check_stats['same_account_count'] += 1
                        continue

                    # 检查1: 在线状态
                    if not await self.check_account_online_status(payment_id):
                        check_stats['offline_count'] += 1
                        self.logger.debug(f"账号{payment_id} -不在线，跳过")
                        continue

                    # 检查2: 释放时间
                    if not self.check_account_release_time(payment_id):
                        check_stats['release_time_count'] += 1
                        self.logger.debug(f"账号{payment_id} -在释放期内，跳过")
                        continue

                    # 检查3: 重复订单检测（直接查询Hash表）
                    self.logger.debug(f"准备检查重复订单: payment_id={payment_id}, target_account={target_account}, amount={amount}")
                    if target_account:
                        duplicate_check = self.check_duplicate_failure(
                            payment_id=payment_id,
                            amount=amount,
                            to_account=target_account,
                            time_window=1200  # 20分钟
                        )

                        if duplicate_check['has_duplicate']:
                            check_stats['duplicate_failure_count'] += 1
                            self.logger.error(
                                f"账号{payment_id}重复订单检测: "
                                f"20分钟内已失败{duplicate_check['duplicate_count']}次 "
                                f"(金额:{amount}, 收款:{target_account})，跳过"
                            )
                            continue
                        else:
                            self.logger.error(
                                f"账号{payment_id}未检测到重复订单，继续使用"
                            )
                    else:
                        self.logger.error(
                            f"账号{payment_id}收款账号为空，跳过重复检测"
                        )

                    # payment_id 锁检查（防止选中已被其他进程占用的账号）
                    lock_key = f'{self.REDIS_KEYS["payment_id_lock_prefix"]}{payment_id}'
                    if self.redis.exists(lock_key):
                        check_stats['payment_id_locked_count'] += 1
                        self.logger.debug(f"账号{payment_id} -payment_id已被锁定，跳过")
                        continue

                    # 检查5: 金额限制和接单限额
                    amount_check = await self.check_account_amount_limits(payment_id, amount)
                    if not amount_check['passed']:
                        if amount_check['reason'] == 'balance_limit_exceeded':
                            check_stats['balance_limit_exceeded_count'] += 1
                            self.logger.debug(f"账号{payment_id} -接单限额检查: {amount_check['reason']}，跳过")
                        else:
                            check_stats['amount_limit_count'] += 1
                            self.logger.debug(f"账号{payment_id} -金额限制: {amount_check['reason']}，跳过")
                        continue

                    # 通过基础检查的账号
                    passed_accounts.append(account_info)
                    self.logger.info(f"账号{payment_id}通过基础检查")

                # 20分钟使用间隔筛选
                if passed_accounts:
                    self.logger.info(f"开始20分钟使用间隔筛选，候选账号数: {len(passed_accounts)}")

                    unused_accounts = []
                    recently_used_accounts = []

                    for account_info in passed_accounts:
                        payment_id = account_info['payment_id']

                        if self.is_account_recently_used(payment_id):
                            last_usage = self.get_account_last_usage_time(payment_id)
                            if last_usage:
                                minutes_ago = (time.time() - last_usage) / 60
                                self.logger.debug(f"账号{payment_id} -在20分钟内使用过({minutes_ago:.1f}分钟前)，暂时排除")
                            else:
                                self.logger.debug(f"账号{payment_id} -在20分钟内使用过，暂时排除")
                            recently_used_accounts.append(account_info)
                            check_stats['recently_used_count'] += 1
                        else:
                            self.logger.debug(f"账号{payment_id} -20分钟内未使用，可优先选择")
                            unused_accounts.append(account_info)

                    # 关键逻辑：如果有未使用的账号，优先使用；否则使用最近使用的账号
                    if unused_accounts:
                        self.logger.info(f"选择20分钟内未使用的账号: {len(unused_accounts)}个可选")
                        available_accounts.append(unused_accounts[0])
                        selected_account = unused_accounts[0]
                        check_stats['available_count'] += 1
                        self.logger.info(f"最终选择账号: payment_id={selected_account['payment_id']} phone={selected_account['phone']}, 余额={selected_account['balance']} (20分钟内未使用)")
                    else:
                        self.logger.warning(f"所有账号都在20分钟内使用过，选择最近使用的账号")
                        if recently_used_accounts:
                            available_accounts.append(recently_used_accounts[0])
                            selected_account = recently_used_accounts[0]
                            check_stats['available_count'] += 1
                            self.logger.info(f"最终选择账号: payment_id={selected_account['payment_id']} phone={selected_account['phone']}, 余额={selected_account['balance']} (虽然20分钟内使用过，但无其他选择)")

            # 如果未找到可用账号，记录详细原因
            if not available_accounts:
                self.logger.warning(f"未找到可用账号")
                if not high_balance_accounts:
                    self.logger.error(f"有序集合中无余额>={amount}的账号")
                else:
                    self.logger.error(f"有序集合有{len(high_balance_accounts)}个高余额账号，但都不满足其他条件")
                    self.logger.error(f"   - 离线账号: {check_stats['offline_count']}")
                    self.logger.error(f"   - 释放期账号: {check_stats['release_time_count']}")
                    self.logger.error(f"   - 重复失败账号: {check_stats['duplicate_failure_count']}")
                    self.logger.error(f"   - payment_id已锁定: {check_stats['payment_id_locked_count']}")
                    self.logger.error(f"   - 金额限制账号: {check_stats['amount_limit_count']}")
                    self.logger.error(f"   - 接单限额超限: {check_stats['balance_limit_exceeded_count']}")
                    self.logger.error(f"   - 收付款相同账号: {check_stats['same_account_count']}")
                    self.logger.error(f"   - 20分钟内使用过: {check_stats['recently_used_count']}")

            # 输出详细统计
            self.logger.info(f"======== EasyPaisa账号筛选完成 ========")
            self.logger.info(f"筛选统计: 总尝试={check_stats['total_attempted']}, 可用={check_stats['available_count']}")

            return available_accounts

        except Exception as e:
            self.logger.error(f"======== EasyPaisa账号筛选异常 ========")
            self.logger.error(f"异常详情: {e}")
            return []

    # ========== Prepare Account and Locks ==========

    async def prepare_account_and_locks(self, order_data: Dict) -> Dict:
        """
        为订单准备账号并获取必要的锁
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
            accounts = await self.get_available_accounts(amount, target_account)

            # 新增代付专卡专户过滤
            target_payment_filtered_accounts = []
            if order_data.get('target_payment'):
                target_payment_filtered_accounts = [account for account in accounts if account['payment_id'] in order_data['target_payment'].split(',')]
            else:
                target_payment_key: str = (self.redis.get("target_payment_key") or b"").decode()
                target_payment_filtered_accounts = [account for account in accounts if account['payment_id'] not in target_payment_key.split(',')]
            accounts = target_payment_filtered_accounts

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

            # 3. 获取订单锁（有可用账号后才获取）
            order_lock_value = self.get_lock(order_code)
            if not order_lock_value:
                return {
                    'success': False,
                    'message': f'订单{order_code} 未抢到订单锁'
                }

            self.logger.info(f"订单{order_code} 成功获取订单锁")

            # 4. 获取账号锁
            account_lock = await self.acquire_account_lock(account_id, order_code)
            if not account_lock:
                # 账号锁失败，释放订单锁
                self.del_lock(order_code, order_lock_value)
                return {
                    'success': False,
                    'message': f'订单{order_code} 账号{account_id}被锁定'
                }

            self.logger.info(f"订单{order_code} 成功获取账号锁: {account_id}")

            # 5. 获取 payment_id 锁
            payment_id_lock_value = self.get_payment_id_lock(payment_id)
            if not payment_id_lock_value:
                # payment_id 锁定失败，释放订单锁和账号锁
                self.release_account_lock(account_id, account_lock)
                self.del_lock(order_code, order_lock_value)
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
            self.logger.error(f"订单{order_code} 准备账号和锁失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())

            # 异常时释放已获取的锁（倒序释放）
            if payment_id_lock_value and payment_id:
                try:
                    self.del_payment_id_lock(payment_id, payment_id_lock_value)
                    self.logger.info(f"订单{order_code} 异常时释放 payment_id 锁")
                except Exception as lock_e:
                    self.logger.error(f"释放 payment_id 锁失败: {lock_e}")

            if account_lock and account_id:
                try:
                    self.release_account_lock(account_id, account_lock)
                    self.logger.info(f"订单{order_code} 异常时释放账号锁")
                except Exception as lock_e:
                    self.logger.error(f"释放账号锁失败: {lock_e}")

            if order_lock_value:
                try:
                    self.del_lock(order_code, order_lock_value)
                    self.logger.info(f"订单{order_code} 异常时释放订单锁")
                except Exception as lock_e:
                    self.logger.error(f"释放订单锁失败: {lock_e}")

            return {
                'success': False,
                'message': f'准备账号异常: {str(e)}'
            }

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
        buckets = {a['payment_id']: {'account': a, 'orders': []} for a in accounts_sorted}
        unassigned = []

        for order in orders_sorted:
            amount = Decimal(str(order['amount']))
            best_pid = None
            best_remaining = Decimal('-1')
            for a in accounts_sorted:
                pid = a['payment_id']
                remaining = virtual_balances[pid]
                if remaining >= amount and remaining > best_remaining:
                    best_pid = pid
                    best_remaining = remaining
            if best_pid:
                buckets[best_pid]['orders'].append(order)
                virtual_balances[best_pid] -= amount
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
