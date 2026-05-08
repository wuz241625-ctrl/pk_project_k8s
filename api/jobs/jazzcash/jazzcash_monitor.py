import os
import re
import secrets
import sys
import threading
import time
import uuid
import json
from concurrent.futures import ThreadPoolExecutor
from queue import Queue, Empty

import aiohttp
import redis
import asyncio
import hashlib
import random
import logging
import simplejson
import traceback
from urllib.parse import quote, urlencode
from typing import List, Dict, Any
from logging.handlers import TimedRotatingFileHandler
# 将项目的主目录添加进系统path，才能直接调用application文件夹下面的模块等
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
parent2_dir = os.path.dirname(parent_dir)
sys.path.insert(0, parent2_dir)

import config
from jobs.common.db import DBConnection
from jobs.common.logging_setup import ProgramLogger, TraceIDFilter, setup_high_performance_logging

# JazzCash自动代付监控系统

# 程序名称（用于日志）
PROGRAM_NAME = 'jazzcash_monitor'

# 初始化日志系统
logger, trace_id_filter, file_handler = setup_high_performance_logging(PROGRAM_NAME, use_async=True)



conf = config.get_config()

# 配置参数
API_SERVER_DOMAIN = getattr(conf, 'ospay_api_host', 'http://localhost:8080')

class AutoPayoutMonitor:
    def __init__(self, name):
        self.name = name
        self.hash_key = f"hash_{name}"
        self.set_key = f"set_{name}"
        self.lock_time = 30 # 操作锁的锁定时间
        self.domain = API_SERVER_DOMAIN # 接口域名
        self.logger = logger
        # 如果使用异步日志处理器，可以定期检查状态
        self.log_handler = file_handler
        self.db = DBConnection(conf)


        # 默认检查间隔配置（5分钟）
        self.check_interval = 300  # 5分钟检查一次

        # JazzCash 特定配置
        self._init_jazzcash_config()

        # 连接redis
        self.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')

    def _init_jazzcash_config(self):
        """初始化 JazzCash 自动代付监控特定配置"""
        # 监控配置
        self.balance_cache_ttl = 300  # 余额缓存5分钟

        # JazzCash API配置（与 EasyPaisa 共用凭证，通过端口区分）
        self.api_url = conf.get('jazzcash_api_url', 'http://34.150.42.92:84')
        self.user_id = conf.get('jazzcash_user_id', 'ba08c3c0e4f546ad92dd2c2e8542ca36')
        self.secret_key = conf.get('jazzcash_secret_key', 'ca45b35e132b46b9b68dd55f1ab077de')

        # 添加payment_id到phone的缓存配置
        self.payment_phone_cache = {}  # 缓存payment_id到phone的映射
        self.cache_ttl = 300  # 缓存5分钟
        self.cache_timestamps = {}  # 缓存时间戳

        # Redis键名配置
        self.REDIS_KEYS = {
            'jazzcash_status_prefix': 'jazzcash_status:',         # 状态缓存前缀（仅自动代付监控系统使用）
            'jazzcash_monitor_report': 'jazzcash_monitor_report', # 监控报告（仅自动代付监控系统使用）
            'jazzcash_limits_hash': 'jazzcash_limits_hash',       # 限额数据Hash（仅自动代付监控系统使用）
            # 添加auto_payout.py的锁键配置
            'jazzcash_account_lock_prefix': 'jazzcash_account_lock:', # 账号锁前缀（auto_payout.py使用）
            'payment_id_lock_prefix': 'payment_id_lock:',           # Payment ID锁前缀（auto_payout.py使用）
        }

    # ==================== JazzCash 自动代付监控相关方法 ====================

    def check_auto_payout_locks(self, account_id: str, payment_id: str) -> dict:
        """
        检查账号是否被auto_payout.py锁定
        返回锁状态信息，用于决定是否可以进行监控操作
        """
        try:
            lock_info = {
                'account_locked': False,
                'payment_id_locked': False,
                'can_monitor': True,
                'lock_details': {}
            }

            # 检查账号锁（使用手机号作为account_id）
            account_lock_key = f"{self.REDIS_KEYS['jazzcash_account_lock_prefix']}{account_id}"
            account_lock_value = self.redis.get(account_lock_key)
            if account_lock_value:
                lock_info['account_locked'] = True
                lock_info['can_monitor'] = False
                lock_info['lock_details']['account_lock'] = {
                    'key': account_lock_key,
                    'value': account_lock_value.decode() if account_lock_value else None,
                    'ttl': self.redis.ttl(account_lock_key)
                }
                self.logger.info(f"账号 {account_id} 被auto_payout.py锁定: {account_lock_value.decode()}")

            # 检查payment_id锁
            payment_lock_key = f"{self.REDIS_KEYS['payment_id_lock_prefix']}{payment_id}"
            payment_lock_value = self.redis.get(payment_lock_key)
            if payment_lock_value:
                lock_info['payment_id_locked'] = True
                lock_info['can_monitor'] = False
                lock_info['lock_details']['payment_id_lock'] = {
                    'key': payment_lock_key,
                    'value': payment_lock_value.decode() if payment_lock_value else None,
                    'ttl': self.redis.ttl(payment_lock_key)
                }
                self.logger.info(f"Payment ID {payment_id} 被auto_payout.py锁定: {payment_lock_value.decode()}")

            return lock_info

        except Exception as e:
            self.logger.error(f"检查auto_payout.py锁失败: {e}")
            # 出错时为了安全，返回不能监控
            return {
                'account_locked': False,
                'payment_id_locked': False,
                'can_monitor': False,
                'error': str(e)
            }

    def test_lock_mechanism(self, account_id: str = "test_account", payment_id: str = "test_payment"):
        """
        测试锁机制是否正常工作
        用于调试和验证锁检查功能
        """
        try:
            self.logger.info("=== 测试锁机制 ===")

            # 1. 测试无锁状态
            lock_info = self.check_auto_payout_locks(account_id, payment_id)
            self.logger.info(f"无锁状态测试: can_monitor={lock_info['can_monitor']}")

            # 2. 模拟账号锁
            account_lock_key = f"{self.REDIS_KEYS['jazzcash_account_lock_prefix']}{account_id}"
            self.redis.setex(account_lock_key, 60, "test_order_123_abcd1234")
            lock_info = self.check_auto_payout_locks(account_id, payment_id)
            self.logger.info(f"账号锁测试: can_monitor={lock_info['can_monitor']}, account_locked={lock_info['account_locked']}")

            # 3. 模拟payment_id锁
            payment_lock_key = f"{self.REDIS_KEYS['payment_id_lock_prefix']}{payment_id}"
            self.redis.setex(payment_lock_key, 60, "test_value_5678efgh")
            lock_info = self.check_auto_payout_locks(account_id, payment_id)
            self.logger.info(f"双锁测试: can_monitor={lock_info['can_monitor']}, both_locked={lock_info['account_locked'] and lock_info['payment_id_locked']}")

            # 4. 清理测试锁
            self.redis.delete(account_lock_key)
            self.redis.delete(payment_lock_key)
            lock_info = self.check_auto_payout_locks(account_id, payment_id)
            self.logger.info(f"清理后测试: can_monitor={lock_info['can_monitor']}")

            self.logger.info("=== 锁机制测试完成 ===")
            return True

        except Exception as e:
            self.logger.error(f"测试锁机制失败: {e}")
            return False

    def _get_db_connection(self):
        return self.db.connection

    async def get_online_payments_from_db(self):
        """从数据库获取在线状态的payment账号"""
        try:
            connection = self._get_db_connection()

            try:
                with connection.cursor() as cur:
                    sql = """
                        SELECT id, phone, account, name, bank_type, bank_type_id, partner_id,
                               wallet_status
                        FROM payment
                        WHERE wallet_status = 1
                          AND (bank_type = 98 OR bank_type_id = 98)
                        ORDER BY id
                    """

                    cur.execute(sql)
                    results = cur.fetchall()

                    self.logger.info(f"从数据库获取到 {len(results)} 个在线payment账号")
                    return results

            finally:
                connection.commit()

        except Exception as e:
            self.logger.error(f"从数据库获取payment账号失败: {e}")
            return []

    def get_phone_by_payment_id(self, payment_id):
        """通过payment_id查询手机号和相关信息"""
        import time

        start_time = time.time()
        self.logger.info(f"开始查询payment_id: {payment_id} 的详细信息")

        try:
            connection = self._get_db_connection()

            try:
                with connection.cursor() as cur:
                    sql = """
                        SELECT phone, account, name, bank_type, partner_id, status, certified
                        FROM payment
                        WHERE id = %s
                    """
                    self.logger.info(f"执行SQL查询: payment_id={payment_id}")
                    self.logger.info(f"SQL语句: {sql.strip()}")

                    query_start = time.time()
                    cur.execute(sql, payment_id)
                    result = cur.fetchone()
                    query_time = time.time() - query_start

                    if result:
                        self.logger.info(f"查询成功! payment_id={payment_id}, 查询耗时: {query_time:.3f}s")
                        self.logger.info(f"查询结果:")
                        self.logger.info(f"   手机号: {result['phone']}")
                        self.logger.info(f"   账号: {result['account']}")
                        self.logger.info(f"   姓名: {result['name']}")
                        self.logger.info(f"   银行类型: {result['bank_type']}")
                        self.logger.info(f"   合作伙伴ID: {result['partner_id']}")
                        self.logger.info(f"   状态: {result['status']} (认证: {result['certified']})")

                        # 检查状态是否符合使用条件
                        if result['status'] == 1 and result['certified'] == 1:
                            self.logger.info(f"账号状态正常，可以使用")
                        else:
                            self.logger.warning(f"账号状态异常: status={result['status']}, certified={result['certified']}")

                        return result
                    else:
                        self.logger.warning(f"payment_id {payment_id} 在数据库中不存在")
                        return None
            finally:
                connection.commit()
                total_time = time.time() - start_time
                self.logger.info(f"数据库查询总耗时: {total_time:.3f}s")

        except Exception as e:
            total_time = time.time() - start_time
            self.logger.error(f"查询payment_id {payment_id} 失败: {e}, 耗时: {total_time:.3f}s")
            import traceback
            self.logger.error(f"详细错误信息: {traceback.format_exc()}")
            return None

    # 添加缓存版本的查询方法，提高性能

    def get_phone_by_payment_id_cached(self, payment_id):
        """带缓存的payment_id查询方法"""
        import time

        current_time = time.time()
        cache_key = str(payment_id)

        self.logger.info(f"尝试从缓存获取payment_id: {payment_id} 的信息")
        self.logger.info(f"缓存键: {cache_key}")
        self.logger.info(f"当前缓存统计: 总条目数={len(self.payment_phone_cache)}, TTL={self.cache_ttl}s")

        # 检查缓存是否有效
        if cache_key in self.payment_phone_cache:
            if cache_key in self.cache_timestamps:
                cache_age = current_time - self.cache_timestamps[cache_key]
                self.logger.info(f"缓存存在，缓存年龄: {cache_age:.1f}s / {self.cache_ttl}s")

                if cache_age < self.cache_ttl:
                    cached_result = self.payment_phone_cache[cache_key]
                    self.logger.info(f"缓存命中! payment_id={payment_id}")
                    self.logger.info(f"缓存的手机号: {cached_result.get('phone', 'N/A')}")
                    self.logger.info(f"缓存的姓名: {cached_result.get('name', 'N/A')}")
                    return cached_result
                else:
                    self.logger.info(f"缓存已过期 ({cache_age:.1f}s > {self.cache_ttl}s)，需要重新查询")
            else:
                self.logger.warning(f"缓存数据存在但时间戳缺失，删除无效缓存")
                del self.payment_phone_cache[cache_key]
        else:
            self.logger.info(f"缓存未命中，payment_id={payment_id} 不在缓存中")

        # 缓存失效或不存在，查询数据库
        self.logger.info(f"缓存失效，开始数据库查询...")
        payment_info = self.get_phone_by_payment_id(payment_id)

        if payment_info:
            self.logger.info(f"查询成功，更新缓存: payment_id={payment_id}")
            self.payment_phone_cache[cache_key] = payment_info
            self.cache_timestamps[cache_key] = current_time

            # 清理过期缓存项
            expired_keys = []
            for k, timestamp in self.cache_timestamps.items():
                if current_time - timestamp >= self.cache_ttl:
                    expired_keys.append(k)

            if expired_keys:
                self.logger.info(f"清理 {len(expired_keys)} 个过期缓存项")
                for k in expired_keys:
                    self.payment_phone_cache.pop(k, None)
                    self.cache_timestamps.pop(k, None)

            self.logger.info(f"缓存更新完成，当前缓存大小: {len(self.payment_phone_cache)} 项")
        else:
            self.logger.warning(f"数据库查询失败，payment_id={payment_id} 不会被缓存")

        return payment_info

    def check_payment_status_in_db(self, payment_id):
        """检查payment在数据库中的状态是否仍然在线"""
        import time

        start_time = time.time()
        self.logger.debug(f"检查payment_id: {payment_id} 的数据库状态")

        try:
            connection = self._get_db_connection()

            try:
                with connection.cursor() as cur:
                    sql = """
                        SELECT status, certified
                        FROM payment
                        WHERE id = %s
                    """

                    cur.execute(sql, payment_id)
                    result = cur.fetchone()

                    if result:
                        is_online = result['status'] == 1 and result['certified'] == 1
                        self.logger.debug(f"payment_id {payment_id} 数据库状态: status={result['status']}, certified={result['certified']}, is_online={is_online}")
                        return is_online
                    else:
                        self.logger.warning(f"payment_id {payment_id} 在数据库中不存在")
                        return False

            finally:
                connection.commit()
                query_time = time.time() - start_time
                self.logger.debug(f"payment_id {payment_id} 状态检查耗时: {query_time:.3f}s")

        except Exception as e:
            query_time = time.time() - start_time
            self.logger.error(f"检查payment_id {payment_id} 数据库状态失败: {e}, 耗时: {query_time:.3f}s")
            # 出错时为了安全，返回False（不在线）
            return False

    async def get_online_jazzcash_accounts(self):
        """从hash_{self.name}中获取已登录成功的JazzCash账号列表"""
        if self.name != 'jazzcash':
            return []

        try:
            # 1. 从Redis Hash中获取所有已登录账号
            hash_data = self.redis.hgetall(self.hash_key)

            if not hash_data:
                self.logger.info(f"{self.hash_key}中没有已登录的JazzCash账号")
                return []

            # 转换为账号对象列表
            accounts = []
            for account_id, login_data_str in hash_data.items():
                try:
                    # 解码账号ID
                    if isinstance(account_id, bytes):
                        account_id = account_id.decode()

                    # 解析登录数据
                    login_data = simplejson.loads(login_data_str.decode() if isinstance(login_data_str, bytes) else login_data_str)

                    # 只处理状态为 loginSuccessful 的账号（已登录成功）
                    if login_data.get('status') != 'loginSuccessful':
                        self.logger.debug(f"账号 {account_id} 状态为 {login_data.get('status')}，跳过监控")
                        continue

                    # 🔥 现在account_id是payment_id（数字），需要查询手机号
                    payment_id = account_id
                    payment_info = self.get_phone_by_payment_id_cached(payment_id)

                    if not payment_info or not payment_info.get('phone'):
                        self.logger.warning(f"payment_id {payment_id} 无法获取手机号，跳过监控")
                        continue

                    phone = payment_info['phone']

                    # 构造账号信息
                    account_info = {
                        'id': payment_id,  # payment.id（数字）
                        'account_name': f'JazzCash_{phone}',  # 使用手机号显示
                        'phone': phone,  # 从数据库查询的手机号
                        'jazzcash_id': phone,  # JazzCash使用手机号
                        'payment_id': payment_id,  # 保存payment_id用于其他操作
                        'min_balance': 1000.00,  # 默认最低余额
                        'status': login_data.get('status'),
                        'partner_id': login_data.get('partner_id'),
                        'login_data': login_data  # 保存完整的登录数据
                    }
                    accounts.append(account_info)

                except Exception as e:
                    self.logger.error(f"解析账号数据失败 {account_id}: {e}")
                    continue

            self.logger.info(f"从{self.hash_key}获取到 {len(accounts)} 个已登录账号: {[a['id'] for a in accounts]}")
            return accounts

        except Exception as e:
            self.logger.error(f"获取在线JazzCash账号列表失败: {e}")
            return []

    async def check_account_health(self, login_data):
        """检查单个账号的健康状态"""
        from datetime import datetime
        from decimal import Decimal

        payment_id = login_data['id']  # 现在是payment.id（数字）

        # 🔥 通过payment_id查询手机号信息
        payment_info = self.get_phone_by_payment_id_cached(payment_id)
        if not payment_info or not payment_info.get('phone'):
            return {
                'account_id': payment_id,
                'account_name': f"JazzCash_{payment_id}",
                'phone': 'UNKNOWN',
                'jazzcash_id': payment_id,
                'check_time': datetime.now().isoformat(),
                'is_online': False,
                'balance': Decimal('0.00'),
                'status': 'phone_not_found',
                'error_message': f'无法获取payment_id {payment_id} 的手机号信息',
                'api_response_time': 0
            }

        phone = payment_info['phone']
        account_name = f"JazzCash_{phone}"  # 使用手机号显示

        try:
            self.logger.info(f"检查账号 payment_id:{payment_id} phone:{phone} ({account_name}) 的健康状态")

            # 初始化状态信息，使用查询到的手机号
            status_info = {
                'account_id': payment_id,  # 保持使用payment_id作为标识符
                'account_name': account_name,
                'phone': phone,  # 从数据库查询的手机号
                'jazzcash_id': phone,  # JazzCash使用手机号
                'payment_id': payment_id,  # 额外保存payment_id
                'check_time': datetime.now().isoformat(),
                'is_online': False,
                'balance': Decimal('0.00'),
                'status': 'offline',
                'error_message': None,
                'api_response_time': 0
            }

            # 🔥 1. 调用JazzCash API检查账号状态和余额（带重试机制）
            max_retries = 4  # 最多重试4次
            retry_delay = 1  # 每次重试间隔1秒
            api_result = None

            for attempt in range(max_retries):
                self.logger.info(f"账号 {payment_id} 余额查询 - 第 {attempt + 1} 次尝试")
                try:
                    api_result = await self.call_jazzcash_balance_api(login_data)

                    # 如果是423错误且还有重试机会，则重试
                    if api_result and api_result.get('should_retry'):
                        if attempt < max_retries - 1:
                            self.logger.warning(
                                f"账号 {payment_id} 遇到 423 错误，{retry_delay}秒后进行第 {attempt + 2} 次重试"
                            )
                            await asyncio.sleep(retry_delay)
                            continue
                        else:
                            # 重试后仍然失败
                            self.logger.error(f"账号 {payment_id} 重试 {max_retries} 次后仍收到 423 错误")

                    # 成功或其他非423错误，跳出重试循环
                    break

                except Exception as e:
                    self.logger.error(f"账号 {payment_id} 余额查询异常: {e}")
                    api_result = {'success': False, 'error': str(e)}
                    break

            # 🔥 2. 调用限额查询API（带重试机制）
            limits_result = None

            for attempt in range(max_retries):
                try:
                    limits_result = await self.call_jazzcash_limits_api(login_data)

                    # 如果是423错误且还有重试机会，则重试
                    if limits_result and limits_result.get('should_retry'):
                        if attempt < max_retries - 1:
                            self.logger.warning(
                                f"账号 {payment_id} 限额查询遇到 423 错误，{retry_delay}秒后重试"
                            )
                            await asyncio.sleep(retry_delay)
                            continue
                        else:
                            self.logger.error(f"账号 {payment_id} 限额查询重试 {max_retries} 次后仍失败")

                    # 成功或其他非423错误，跳出重试循环
                    break

                except Exception as e:
                    self.logger.error(f"账号 {payment_id} 限额查询异常: {e}")
                    limits_result = {'success': False, 'error': str(e)}
                    break

            # 3. 处理余额查询结果
            if api_result and api_result.get('success'):
                # ✅ API调用成功
                status_info.update({
                    'is_online': True,
                    'balance': Decimal(str(api_result.get('balance', 0))),
                    'status': 'online',
                    'api_response_time': api_result.get('response_time', 0)
                })
                self.logger.info(f"账号 payment_id:{payment_id} phone:{phone} 余额查询成功，当前余额: {status_info['balance']}")

            elif api_result and api_result.get('should_offline'):
                # ❌ 501错误 - 账号无效，强制下线
                status_info.update({
                    'is_online': False,
                    'status': 'account_invalid',
                    'error_message': api_result.get('error', '账号无效(501)'),
                    'api_response_time': api_result.get('response_time', 0),
                    'force_offline': True
                })
                self.logger.warning(f"账号 payment_id:{payment_id} phone:{phone} 收到501错误，将强制下线: {api_result.get('error')}")

            else:
                # ❌ API调用失败（包括423错误、其他错误）
                status_info.update({
                    'is_online': False,
                    'status': 'api_error',
                    'error_message': api_result.get('error', 'API调用失败') if api_result else 'API无响应',
                    'api_response_time': api_result.get('response_time', 0) if api_result else 0
                })

                # 根据错误类型输出不同的日志
                if api_result and api_result.get('should_retry'):
                    self.logger.warning(f"账号 payment_id:{payment_id} phone:{phone} 重试{max_retries}次后仍收到423错误，将执行下线: {api_result.get('error')}")
                else:
                    self.logger.warning(f"账号 payment_id:{payment_id} phone:{phone} API调用失败: {api_result.get('error') if api_result else 'API无响应'}")

            # 🔥 3. 处理限额查询结果（独立保存，不影响status_info）
            if isinstance(limits_result, Exception):
                # 限额查询异常
                self.logger.error(f"账号 payment_id:{payment_id} 限额查询异常: {limits_result}")
            elif limits_result and limits_result.get('success'):
                # 限额查询成功，保存到Redis
                limits_data = limits_result.get('limits', {})
                limits_data['phone'] = phone
                limits_data['query_time'] = datetime.now().isoformat()
                limits_data['response_time'] = limits_result.get('response_time', 0)

                # 🔥 直接保存到Redis（独立的Hash），不放入status_info
                await self.save_limits_to_redis(payment_id, limits_data)
                self.logger.info(f"账号 payment_id:{payment_id} 限额查询成功并已保存到Redis")
            else:
                # 限额查询失败
                error = limits_result.get('error') if isinstance(limits_result, dict) else str(limits_result)
                self.logger.warning(f"账号 payment_id:{payment_id} 限额查询失败: {error}")

            self.logger.info(f"账号 payment_id:{payment_id} phone:{phone} 检查完成: {status_info['status']}, 余额: {status_info['balance']}")
            return status_info

        except Exception as e:
            self.logger.error(f"检查账号 payment_id:{payment_id} 健康状态异常: {e}")
            return {
                'account_id': payment_id,
                'account_name': account_name,
                'check_time': datetime.now().isoformat(),
                'is_online': False,
                'balance': Decimal('0.00'),
                'status': 'check_error',
                'error_message': str(e),
                'api_response_time': 0
            }

    async def _post_jazzcash_api(self, form_data, login_data):
        """Direct aiohttp POST to JazzCash API. Retry once on failure."""
        for attempt in range(2):
            try:
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=30),
                    connector=aiohttp.TCPConnector(ssl=False)
                ) as session:
                    async with session.post(self.api_url, data=form_data) as resp:
                        if 200 <= resp.status < 300:
                            text = await resp.text()
                            return simplejson.loads(text) if text else None
            except Exception as e:
                self.logger.error(f"网络请求错误: uid: {login_data['id']}; {e}")
            if attempt == 0:
                await asyncio.sleep(0.5)
        return None

    async def call_jazzcash_balance_api(self, login_data):
        """调用JazzCash余额查询API（按照JazzCash文档格式）"""
        import base64
        import hashlib

        try:
            payment_id = login_data['id']  # 现在是payment.id（数字）

            # 🔥 通过payment_id查询手机号
            payment_info = self.get_phone_by_payment_id_cached(payment_id)
            if not payment_info or not payment_info.get('phone'):
                self.logger.error(f"payment_id {payment_id} 无法获取手机号信息")
                return {
                    'success': False,
                    'error': f'无法获取payment_id {payment_id} 的手机号信息',
                    'response_time': 0
                }

            phone = payment_info['phone']  # 从数据库查询到的手机号
            self.logger.debug(f"payment_id {payment_id} 对应的手机号: {phone}")

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

            # 构造FormBody格式（按照JazzCash文档）
            data_b64 = base64.b64encode(json.dumps(inner_payload).encode()).decode()

            # 计算MD5签名
            sign_string = data_b64 + self.secret_key
            sign = hashlib.md5(sign_string.encode()).hexdigest()

            form_data = {
                'user_id': self.user_id,
                'data': data_b64,
                'sign': sign
            }

            self.logger.info(f"调用JazzCash余额API: account_id={phone}, api_url={self.api_url}")

            start_time = time.time()
            result = await self._post_jazzcash_api(form_data, login_data)
            response_time = time.time() - start_time

            if result is None:
                self.logger.error(f"API无响应")
                return {
                    'success': False,
                    'error': 'API无响应',
                    'response_time': response_time
                }

            if result.get('code') == 200:
                # 根据JazzCash文档，余额在 data.data.avaliableBalance 字段
                data = result.get('data', {})
                # JazzCash 响应结构: {"code": 200, "data": {"data": {"avaliableBalance": "852.75"}}}
                inner_data = data.get('data', {}) if isinstance(data, dict) else {}
                # 注意：API 返回的是 avaliableBalance（拼写错误，但这是实际返回）
                balance = inner_data.get('avaliableBalance', inner_data.get('availableBalance', 0))

                self.logger.info(f"余额查询成功: payment_id={payment_id}, balance={balance}")
                return {
                    'success': True,
                    'balance': balance,
                    'response_time': response_time,
                    'data': result
                }
            elif result.get('code') == 501:
                # 501 AccountInvalid - 账号无效，需要下线
                error_msg = result.get('msg', result.get('message', '账号无效(501)'))
                self.logger.error(f"账号无效: payment_id={payment_id}, error={error_msg}")
                return {
                    'success': False,
                    'error': error_msg,
                    'response_time': response_time,
                    'data': result,
                    'should_offline': True  # 标记需要下线
                }
            elif result.get('code') == 423:
                # 423 ServerBusy - 服务器忙
                error_msg = result.get('msg', result.get('message', '服务器忙(423)'))
                self.logger.warning(f"服务器忙: payment_id={payment_id}, error={error_msg}")
                return {
                    'success': False,
                    'error': error_msg,
                    'response_time': response_time,
                    'data': result,
                    'should_retry': True  # 标记需要重试
                }
            else:
                error_msg = result.get('msg', result.get('message', 'API返回错误'))
                self.logger.error(f"API错误: payment_id={payment_id}, code={result.get('code')}, error={error_msg}")
                return {
                    'success': False,
                    'error': error_msg,
                    'response_time': response_time,
                    'data': result
                }

        except Exception as e:
            self.logger.error(f"调用JazzCash余额API异常: {e}")
            import traceback
            self.logger.error(f"异常堆栈: {traceback.format_exc()}")
            return {
                'success': False,
                'error': str(e),
                'response_time': 0
            }

    async def call_jazzcash_limits_api(self, login_data):
        """调用JazzCash限额查询API"""
        import base64
        import hashlib

        try:
            payment_id = login_data['id']

            # 🔥 通过payment_id查询手机号
            payment_info = self.get_phone_by_payment_id_cached(payment_id)
            if not payment_info or not payment_info.get('phone'):
                self.logger.error(f"payment_id {payment_id} 无法获取手机号信息")
                return {
                    'success': False,
                    'error': f'无法获取payment_id {payment_id} 的手机号信息',
                    'response_time': 0
                }

            phone = payment_info['phone']
            self.logger.debug(f"payment_id {payment_id} 限额查询，使用手机号: {phone}")

            # 构造payload数据（限额查询只需要account_id）
            payload_data = {
                "account_id": phone  # 手机号
            }

            # 构造内层payload
            inner_payload = {
                "id": str(uuid.uuid4()),  # 生成UUID
                "action": "queryLimits",  # 🔥 限额查询接口
                "payload": payload_data
            }

            # 构造FormBody格式（按照JazzCash文档）
            data_b64 = base64.b64encode(json.dumps(inner_payload).encode()).decode()

            # 计算MD5签名
            sign_string = data_b64 + self.secret_key
            sign = hashlib.md5(sign_string.encode()).hexdigest()

            form_data = {
                'user_id': self.user_id,
                'data': data_b64,
                'sign': sign
            }

            self.logger.info(f"调用JazzCash限额API: payment_id={payment_id}, account_id={phone}, api_url={self.api_url}")

            start_time = time.time()
            result = await self._post_jazzcash_api(form_data, login_data)
            response_time = time.time() - start_time

            if result is None:
                self.logger.error(f"限额API无响应: payment_id={payment_id}")
                return {
                    'success': False,
                    'error': 'API无响应',
                    'response_time': response_time
                }

            if result.get('code') == 200:
                # 🔥 根据实际API返回，限额在 data.data.accountLimits 和 data.data.remainingLimits
                data = result.get('data', {})
                inner_data = data.get('data', {}) if isinstance(data, dict) else {}

                # 提取限额信息（accountLimits 是总限额，remainingLimits 是剩余限额）
                account_limits = inner_data.get('accountLimits', {})
                remaining_limits = inner_data.get('remainingLimits', {})

                # 转换为前端兼容格式（debit=转出/发送, credit=转入/接收）
                # 前端显示格式：剩余/总额
                limits_info = {
                    # 前端兼容字段（debit=转出/发送, credit=转入/接收）
                    # debitDaily = 剩余的日转出限额
                    'debitDaily': remaining_limits.get('dailySendingLimit', '0'),
                    'debitDailyThreshold': account_limits.get('dailySendingLimit', '0'),
                    'debitMonthly': remaining_limits.get('monthlySendingLimit', '0'),
                    'debitMonthlyThreshold': account_limits.get('monthlySendingLimit', '0'),
                    'debitYearly': remaining_limits.get('yearlySendingLimit', '0'),
                    'debitYearlyThreshold': account_limits.get('yearlySendingLimit', '0'),
                    # creditDaily = 剩余的日转入限额
                    'creditDaily': remaining_limits.get('dailyReceivingLimit', '0'),
                    'creditDailyThreshold': account_limits.get('dailyReceivingLimit', '0'),
                    'creditMonthly': remaining_limits.get('monthlyReceivingLimit', '0'),
                    'creditMonthlyThreshold': account_limits.get('monthlyReceivingLimit', '0'),
                    'creditYearly': remaining_limits.get('yearlyReceivingLimit', '0'),
                    'creditYearlyThreshold': account_limits.get('yearlyReceivingLimit', '0'),
                }

                self.logger.info(f"限额查询成功: payment_id={payment_id}, 日转出限额={limits_info['debitDaily']}/{limits_info['debitDailyThreshold']}, 月转出限额={limits_info['debitMonthly']}/{limits_info['debitMonthlyThreshold']}, 日转入限额={limits_info['creditDaily']}/{limits_info['creditDailyThreshold']}")
                return {
                    'success': True,
                    'limits': limits_info,
                    'response_time': response_time,
                    'data': result
                }
            elif result.get('code') == 501:
                # 501 AccountInvalid - 账号无效
                error_msg = result.get('msg', result.get('message', '账号无效(501)'))
                self.logger.error(f"限额查询-账号无效: payment_id={payment_id}, error={error_msg}")
                return {
                    'success': False,
                    'error': error_msg,
                    'response_time': response_time,
                    'data': result,
                    'should_offline': True  # 标记需要下线
                }
            elif result.get('code') == 423:
                # 423 ServerBusy - 服务器忙
                error_msg = result.get('msg', result.get('message', '服务器忙(423)'))
                self.logger.warning(f"限额查询-服务器忙: payment_id={payment_id}, error={error_msg}")
                return {
                    'success': False,
                    'error': error_msg,
                    'response_time': response_time,
                    'data': result,
                    'should_retry': True  # 标记可以重试
                }
            else:
                # 其他错误
                error_msg = result.get('msg', result.get('message', f"未知错误(code:{result.get('code')})"))
                self.logger.error(f"限额查询API错误: payment_id={payment_id}, code={result.get('code')}, error={error_msg}")
                return {
                    'success': False,
                    'error': error_msg,
                    'response_time': response_time,
                    'data': result
                }

        except Exception as e:
            self.logger.error(f"调用JazzCash限额API异常: {e}")
            import traceback
            self.logger.error(f"异常堆栈: {traceback.format_exc()}")
            return {
                'success': False,
                'error': str(e),
                'response_time': 0
            }

    async def save_limits_to_redis(self, payment_id, limits_data):
        """保存限额数据到Redis Hash"""
        try:
            from datetime import datetime

            limits_hash_key = self.REDIS_KEYS['jazzcash_limits_hash']

            # 构造完整的限额数据记录（使用前端兼容字段）
            limits_record = {
                'payment_id': str(payment_id),
                'phone': limits_data.get('phone', ''),
                # 前端兼容字段（debit=转出/发送, credit=转入/接收）
                'debitDaily': limits_data.get('debitDaily', '0'),
                'debitDailyThreshold': limits_data.get('debitDailyThreshold', '0'),
                'debitMonthly': limits_data.get('debitMonthly', '0'),
                'debitMonthlyThreshold': limits_data.get('debitMonthlyThreshold', '0'),
                'debitYearly': limits_data.get('debitYearly', '0'),
                'debitYearlyThreshold': limits_data.get('debitYearlyThreshold', '0'),
                'creditDaily': limits_data.get('creditDaily', '0'),
                'creditDailyThreshold': limits_data.get('creditDailyThreshold', '0'),
                'creditMonthly': limits_data.get('creditMonthly', '0'),
                'creditMonthlyThreshold': limits_data.get('creditMonthlyThreshold', '0'),
                'creditYearly': limits_data.get('creditYearly', '0'),
                'creditYearlyThreshold': limits_data.get('creditYearlyThreshold', '0'),
                'query_time': limits_data.get('query_time', datetime.now().isoformat()),
                'update_time': datetime.now().isoformat(),
                'response_time': limits_data.get('response_time', 0)
            }

            # 🔥 存储到Hash：field=payment_id, value=JSON字符串
            self.redis.hset(
                limits_hash_key,
                str(payment_id),
                json.dumps(limits_record)
            )

            # 🔥 不设置过期时间，永久保存限额数据用于历史查询
            # self.redis.expire(limits_hash_key, self.limits_cache_ttl)

            self.logger.info(f"限额数据已保存到Redis: payment_id={payment_id}, 日转出限额={limits_record['debitDaily']}/{limits_record['debitDailyThreshold']}, 月转出限额={limits_record['debitMonthly']}/{limits_record['debitMonthlyThreshold']}, 日转入限额={limits_record['creditDaily']}/{limits_record['creditDailyThreshold']}")
            return True

        except Exception as e:
            self.logger.error(f"保存限额数据到Redis失败: payment_id={payment_id}, error={e}")
            import traceback
            self.logger.error(f"异常堆栈: {traceback.format_exc()}")
            return False

    def get_limits_from_redis(self, payment_id):
        """从Redis获取指定账号的限额数据"""
        try:
            limits_hash_key = self.REDIS_KEYS['jazzcash_limits_hash']
            limits_json = self.redis.hget(limits_hash_key, str(payment_id))

            if limits_json:
                limits_data = json.loads(limits_json.decode() if isinstance(limits_json, bytes) else limits_json)
                return limits_data
            else:
                return None

        except Exception as e:
            self.logger.error(f"从Redis获取限额数据失败: payment_id={payment_id}, error={e}")
            return None

    def update_payment_balance_snapshot(self, payment_id, balance):
        """健康余额查询成功后写入 MySQL payment.balance。"""
        connection = None
        try:
            connection = self.db.connection
            with connection.cursor() as cur:
                affected_rows = cur.execute(
                    """
                    UPDATE payment
                    SET balance = %s,
                        time_update = NOW()
                    WHERE id = %s
                      AND (bank_type = 98 OR bank_type = '98' OR bank_type_id = 98)
                    """,
                    (balance, payment_id),
                )
            connection.commit()
            self.logger.info(f"JazzCash 健康余额写入 MySQL: payment_id={payment_id}, balance={balance}, affected={affected_rows}")
            return affected_rows
        except Exception as e:
            if connection:
                connection.rollback()
            self.logger.error(f"JazzCash 健康余额写入 MySQL 失败 payment_id={payment_id}: {e}")
            return 0

    async def update_redis_cache(self, status_info):
        """更新健康结果：业务余额写 MySQL，Redis 只保留短期状态缓存。"""
        try:
            account_id = status_info['account_id']

            # 先判断是否正常
            if status_info['is_online'] and status_info['status'] == 'online':
                # 200成功：余额落 MySQL，状态只做短期缓存。
                balance = status_info['balance']
                self.update_payment_balance_snapshot(account_id, balance)

                # 更新状态缓存（包含余额）
                status_key = f"{self.REDIS_KEYS['jazzcash_status_prefix']}{account_id}"
                status_data = {
                    'status': status_info['status'],
                    'balance': str(status_info['balance']),
                    'check_time': status_info['check_time'],
                    'error_message': status_info['error_message'],
                    'api_response_time': status_info['api_response_time']
                }
                self.redis.setex(status_key, self.balance_cache_ttl, json.dumps(status_data))

                # MySQL 三最终态和 payment.balance 是资格源；Redis 只保留短期状态缓存。

            else:
                # API错误：只更新状态缓存（不包含余额），下线处理
                status_key = f"{self.REDIS_KEYS['jazzcash_status_prefix']}{account_id}"
                status_data = {
                    'status': status_info['status'],
                    'check_time': status_info['check_time'],
                    'error_message': status_info['error_message'],
                    'api_response_time': status_info['api_response_time']
                    # 注意：不包含balance字段，保持原有余额不变
                }
                self.redis.setex(status_key, self.balance_cache_ttl, json.dumps(status_data))

                # 根据错误类型记录日志和特殊处理
                if status_info.get('force_offline'):
                    # 501错误：完全删除账号数据
                    error_msg = status_info.get('error_message', '501账号无效')
                    self.logger.warning(f"账号 {account_id} 因501错误被强制下线: {error_msg}")
                    self.remove_account_completely(account_id, f"501账号无效: {error_msg}")
                    return True  # 返回True表示账号已删除，调用方应停止后续处理
                elif status_info['status'] == 'api_error':
                    self.logger.warning(f"账号 {account_id} 因API错误被下线: {status_info.get('error_message')}")
                else:
                    self.logger.info(f"账号 {account_id} 已下线: {status_info['status']}")

            self.logger.debug(f"账号 {account_id} Redis缓存更新完成")
            return False  # 正常处理，账号未删除

        except Exception as e:
            self.logger.error(f"更新账号 {account_id} Redis缓存失败: {e}")
            return False  # 异常情况，账号未删除

    async def handle_problematic_accounts(self, all_status):
        """处理有问题的账号"""
        try:
            offline_accounts = [s for s in all_status if not s['is_online']]
            error_accounts = [s for s in all_status if 'error' in s['status']]
            invalid_accounts = [s for s in all_status if s['status'] == 'account_invalid']

            if offline_accounts:
                account_names = [s['account_name'] for s in offline_accounts]
                self.logger.warning(f"发现 {len(offline_accounts)} 个离线账号: {account_names}")

            # 代收业务不需要关心余额不足的问题，已删除 low_balance 处理逻辑

            if invalid_accounts:
                for account in invalid_accounts:
                    self.logger.error(f"账号 {account['account_name']} 收到501错误已强制下线: {account['error_message']}")

            if error_accounts:
                for account in error_accounts:
                    if account['status'] != 'account_invalid':  # 避免重复记录501错误
                        self.logger.error(f"账号 {account['account_name']} 检查异常: {account['error_message']}")

        except Exception as e:
            self.logger.error(f"处理问题账号异常: {e}")

    async def generate_monitor_report(self, all_status):
        """生成监控报告"""
        from datetime import datetime

        try:
            total_count = len(all_status)
            online_count = len([s for s in all_status if s['is_online']])
            offline_count = total_count - online_count

            total_balance = sum(s['balance'] for s in all_status)
            online_balance = sum(s['balance'] for s in all_status if s['is_online'])

            avg_response_time = sum(s['api_response_time'] for s in all_status) / total_count if total_count > 0 else 0

            report = {
                'report_time': datetime.now().isoformat(),
                'total_accounts': total_count,
                'online_accounts': online_count,
                'offline_accounts': offline_count,
                'online_rate': f"{online_count/total_count*100:.1f}%" if total_count > 0 else "0%",
                'total_balance': str(total_balance),
                'online_balance': str(online_balance),
                'avg_response_time': f"{avg_response_time:.2f}s"
            }

            # 存储到Redis
            report_key = self.REDIS_KEYS['jazzcash_monitor_report']
            self.redis.hmset(report_key, report)
            self.redis.expire(report_key, 3600)  # 1小时过期

            # 输出报告
            self.logger.info(f"=== JazzCash自动代付账号监控报告 ===")
            self.logger.info(f"总账号: {total_count}, 在线: {online_count}, 离线: {offline_count}")
            self.logger.info(f"在线率: {report['online_rate']}")
            self.logger.info(f"总余额: {total_balance}, 在线余额: {online_balance}")
            self.logger.info(f"平均响应时间: {report['avg_response_time']}")

            return report

        except Exception as e:
            self.logger.error(f"生成监控报告异常: {e}")
            return {}

    async def run_easypaisa_monitor_check(self):
        """执行 JazzCash 监控检查（方法名保留以兼容调用）"""
        return await self.run_jazzcash_monitor_check()

    async def run_jazzcash_monitor_check(self):
        """执行 JazzCash 监控检查"""
        try:
            self.logger.info("=" * 50)
            self.logger.info("开始从 MySQL payment.wallet_status 检查 JazzCash 账号健康状态")

            accounts = await self.get_online_payments_from_db()
            if not accounts:
                self.logger.info("MySQL 中没有 wallet_status=1 的 JazzCash 账号需要检查")
                return

            members = [str(account['id']).encode() for account in accounts if account.get('id') is not None]
            allocated_members = self.get_process_allocated_members(members)
            allocated_ids = {member.decode() for member in allocated_members}
            if not allocated_ids:
                self.logger.info("当前进程没有分配到 JazzCash monitor 账号")
                return
            accounts = [account for account in accounts if str(account.get('id')) in allocated_ids]

            check_tasks = [self.check_account_health(account) for account in accounts]
            all_status = await asyncio.gather(*check_tasks, return_exceptions=True)

            valid_status = []
            for status in all_status:
                if isinstance(status, Exception):
                    self.logger.error(f"账号检查异常: {status}")
                else:
                    valid_status.append(status)

            for status in valid_status:
                await self.update_redis_cache(status)

            await self.handle_problematic_accounts(valid_status)
            await self.generate_monitor_report(valid_status)

            self.logger.info("JazzCash MySQL 钱包健康状态检查完成")

        except Exception as e:
            self.logger.error(f"JazzCash账号状态检查异常: {e}")
            self.logger.error(f"详细错误: {traceback.format_exc()}")

    # ==================== 结束 JazzCash 监控相关方法 ====================

    def get_log_stats(self):
        """获取日志统计信息（如果使用异步处理器）"""
        """获取日志统计信息"""
        if hasattr(self.log_handler, 'get_stats'):
            return self.log_handler.get_stats()
        elif hasattr(self.log_handler, 'buffer'):
            return {
                'buffer_size': len(self.log_handler.buffer),
                'buffer_bytes': getattr(self.log_handler, 'buffer_bytes', 0),
                'is_running': not getattr(self.log_handler, '_shutdown', False)
            }
        return None



    def check_redis_connection(self):
        """检查Redis连接"""
        try:
            redis_response = self.redis.ping()
            if not redis_response:
                self.logger.info(f"bank: {self.name},Redis服务未能ping通,3秒后重新连接")
                self.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
        except Exception as e:
            self.logger.info(f"bank: {self.name},Redis 连接失败,3秒后重试: {e}")
            time.sleep(2)
            self.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
            self.check_redis_connection()  # 递归尝试，不恢复连接不进行下一步

    def check_data_consistency(self):
        """旧 hash/set 一致性检查已退役。"""
        self.logger.info("JazzCash monitor 已切换为 MySQL wallet_status 调度，跳过旧 hash/set 一致性检查")
        return True

    def get_proxies(self):
        try:
            _indian_socks_ip = self.redis.get(f'indian_socks_ip_{self.name}')
            if not _indian_socks_ip:
                self.logger.error(f'无 indian_socks_ip_{self.name}')
                return False
            _indian_socks_ip = _indian_socks_ip.decode().split(',')
            _indian_socks_ip = [item for item in _indian_socks_ip if item.strip()]
            proxy = random.choice(_indian_socks_ip)
            proxies = {
                'http': proxy if proxy.startswith('socks5://') else 'socks5://{}'.format(proxy),
                'https': proxy if proxy.startswith('socks5://') else 'socks5://{}'.format(proxy)
            }
            return proxies
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('get_proxies 脚本运行错误{}\n{}'.format(e, error_message))
            return False



    def get_lock(self, _id):
        try:
            # 获取锁
            busy_key = '{}_operate_{}'.format(self.name, _id)
            _value = secrets.token_hex(8)
            _lock = self.redis.setnx(busy_key, _value) # 返回 0 已存在, 1 不存在且设置成功
            if not _lock:
                # 防止死锁
                _ttl = self.redis.ttl(busy_key)
                self.logger.info(f"{_id}, {busy_key} 剩余生存时间 {_ttl} s")
                if _ttl and int(_ttl) > self.lock_time:
                    self.redis.delete(busy_key)
                    self.logger.error(f"{_id}, 死锁并删除 {_value}")
                return False
            self.redis.expire(busy_key, self.lock_time)
            self.logger.info(f"{_id},{busy_key} 加锁时间 {self.lock_time} s, _value: {_value}")
            return _value
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('get_lock 脚本运行错误{}\n{}\n{}'.format(_id, e, error_message))
            return False

    def del_lock(self, _id, value):
        try:
            # 获取锁，30秒内锁定
            busy_key = '{}_operate_{}'.format(self.name, _id)
            self.logger.info(f"准备删除Lock {busy_key}")
            _lock = self.redis.get(busy_key)
            if _lock and _lock.decode() == value:
                result = self.redis.delete(busy_key)
                self.logger.info(f"删除Lock {busy_key}, result: {result}")
            return True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('del_lock 脚本运行错误{}\n{}\n{}'.format(_id, e, error_message))
            return False



    def remove_account_completely(self, account_id, reason="未知原因"):
        """完全删除账号的所有数据"""
        try:
            # 1. 删除主数据存储
            hash_deleted = self.redis.hdel(self.hash_key, account_id)
            zset_deleted = self.redis.zrem(self.set_key, account_id)

            # 2. 删除JazzCash短期状态缓存；余额最终记录保留在 MySQL payment.balance。
            self.redis.delete(f'jazzcash_status:{account_id}')

            # 3. 删除登录状态键
            self.redis.delete(f'login_on_{self.name}_{account_id}')

            # 🔥 4. 更新数据库payment表状态为下线
            try:
                self.update_payment_status_to_offline(account_id, reason)
            except Exception as db_e:
                self.logger.error(f"更新数据库payment表状态失败: {db_e}")

            self.logger.warning(f"🗑️ 已完全删除账号 {account_id} 的所有数据，原因: {reason}")
            self.logger.info(f"删除详情: hash删除{hash_deleted}项, zset删除{zset_deleted}项")

            return True

        except Exception as e:
            self.logger.error(f"删除账号 {account_id} 数据时出错: {e}")
            return False

    def update_payment_status_to_offline(self, account_id, reason="下线"):
        """更新payment表中账号状态为下线"""
        try:
            connection = self._get_db_connection()

            try:
                with connection.cursor() as cur:
                    # 更新payment表状态为0（下线），并清理最终业务状态
                    sql = """
                        UPDATE payment
                        SET status = 0,
                            wallet_status = 0,
                            collection_status = 0,
                            payout_status = 0,
                            time_update = NOW()
                        WHERE id = %s
                    """

                    affected_rows = cur.execute(sql, (account_id,))
                    connection.commit()

                    if affected_rows > 0:
                        self.logger.info(f"✅ 已将payment表中账号 {account_id} 状态更新为下线，原因: {reason}")
                    else:
                        self.logger.warning(f"⚠️ payment表中未找到账号 {account_id}，可能已被删除")

                    return affected_rows > 0

            finally:
                connection.commit()

        except Exception as e:
            self.logger.error(f"❌ 更新payment表账号 {account_id} 状态失败: {e}")
            return False

    def on_off(self, login_data, _on=1):
        self.logger.info(f"{login_data['id']} on_off(_on={_on}) 处理上下线")
        try:
            if _on == 1:
                self.logger.info(
                    f"{login_data['id']}, {self.name} 在线确认：不写旧 Redis 在线集合，"
                    "钱包采集/代收/代付资格分别由 MySQL wallet_status/collection_status/payout_status 控制"
                )
                return True
            self.logger.error(f"{login_data['id']}, {self.name} 下线确认：MySQL 三最终态控制资格")
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('on_off 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(login_data)))
            return False

    def update_key(self, login_data, next_check_interval=None):
        """
        旧 hash/set 调度兼容入口。
        Args:
            login_data: 账号数据
            next_check_interval: 下次检查间隔（秒），None表示使用默认check_interval
        """
        try:
            self.logger.info(
                f"账号 {login_data.get('id')} JazzCash monitor 已切换为 MySQL wallet_status 调度，"
                "不再写入旧 hash/set 检查队列"
            )
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('update_key() 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(login_data)))

    # 获取列表中的所有元素
    def read_redis_list(self, key):
        # 使用 lrange 获取列表中的所有元素
        elements = self.redis.lrange(key, 0, -1)  # 0 表示第一个元素，-1 表示最后一个元素
        # 将字节字符串解码为普通字符串
        decoded_elements = [element.decode('utf-8') for element in elements]
        # 转换为集合（自动去重）
        element_set = set(decoded_elements)

        # # 打印列表中的元素
        # if elements:
        #     self.logger.info(f"列表 '{key}' 中的元素如下：")
        #     for i, element in enumerate(elements):
        #         # 将字节字符串解码为普通字符串
        #         self.logger.info(f"{i + 1}: {element.decode('utf-8')}")
        # else:
        #     self.logger.info(f"列表 '{key}' 为空或不存在")

        return element_set

    # 打印所有的缓存,比较耗性能,生产环境可注释掉
    def read_cache(self, source, login_data):
        user_id = login_data['id']
        qr_channel = login_data['qr_channel']
        self.logger.info(f"{user_id}, source: {source} 开始读取业务缓存")
        try:
            cache_key_lock = f'{self.name}_operate_{user_id}'
            cache_key_login_on = f'login_on_{self.name}_{user_id}'
            cache_key_upi_active_payment = f'upi_active_payment:{user_id}'
            cache_key_device = f'{self.name}_device'

            self.logger.info(f"{login_data['id']}, read_cache() key: {self.set_key}, 成员 {login_data['id']}, score: {self.redis.zscore(self.set_key, login_data['id'])}, ttl: {self.redis.ttl(self.set_key)}")
            self.logger.info(f"{login_data['id']}, read_cache() key: {self.hash_key}, 成员 {login_data['id']}, hash value: {self.redis.hget(self.hash_key, login_data['id'])}, ttl: {self.redis.ttl(self.hash_key)}")
            self.logger.info(f"{login_data['id']}, read_cache() key: {cache_key_lock}, value: {self.redis.get(cache_key_lock)}, ttl: {self.redis.ttl(cache_key_lock)}")
            self.logger.info(f"{login_data['id']}, read_cache() key: {cache_key_login_on}, value: {self.redis.get(cache_key_login_on)}, ttl: {self.redis.ttl(cache_key_login_on)}")
            self.logger.info(f"{login_data['id']}, read_cache() key: {cache_key_upi_active_payment}, value: {self.redis.get(cache_key_upi_active_payment)}, ttl: {self.redis.ttl(cache_key_upi_active_payment)}")
            self.logger.info(
                f"{login_data['id']}, read_cache() MySQL 三最终态提示：wallet_status/collection_status/payout_status "
                "是钱包采集、代收、代付资格源；旧 payment_online/payment_active/kick_off 不再参与资格判断"
            )
            self.logger.info(f"{login_data['id']}, read_cache() key: {self.hash_key}, 成员 {login_data['id']}, hash value: {self.redis.hget(cache_key_device, login_data['id'])}, ttl: {self.redis.ttl(cache_key_device)}")
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('read_cache 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(login_data)))

    # 打印 Redis 集合中的所有元素，生产环境可注释掉
    def read_zset(self, key):
        elements_with_scores = self.redis.zrange(key, 0, -1, withscores=True)
        # 将元素和分数存储到字典中
        result_dict = {element.decode(): score for element, score in elements_with_scores}
        self.logger.info(f"read_zset() zset key: {key},共{len(result_dict)}个 value: {result_dict}")



























    # 添加多进程分片和并发处理方法
    def get_active_processes_count(self):
        """获取当前活跃进程数量"""
        try:
            # 注册当前进程 (monitor专用键，避免与auto_payout进程冲突)
            process_key = f"active_processes_{self.name}_monitor"
            current_process_id = f"{process_key}:{os.getpid()}"
            self.redis.setex(current_process_id, 30, int(time.time()))

            # 获取所有活跃进程
            active_processes = self.redis.keys(f"{process_key}:*")

            # 提取并排序PID，确保一致性
            pids = []
            for key in active_processes:
                try:
                    pid = int(key.decode().split(':')[-1])
                    pids.append(pid)
                except:
                    continue

            pids.sort()
            current_pid = os.getpid()

            total_processes = len(pids)
            current_index = pids.index(current_pid) if current_pid in pids else 0

            return total_processes, current_index
        except Exception as e:
            self.logger.error(f"获取活跃进程失败: {e}")
            return 1, 0

    def get_process_allocated_members(self, members: List[bytes]) -> List[bytes]:
        """基于进程ID分片分配members"""
        if not members:
            return []

        total_processes, current_index = self.get_active_processes_count()

        if total_processes <= 1:
            return members

        # 使用一致性哈希分配members
        allocated_members = []
        for member in members:
            member_id = member.decode()
            # 使用MD5哈希确保相同member总是分配给同一进程
            hash_value = int(hashlib.md5(member_id.encode()).hexdigest(), 16)
            assigned_index = hash_value % total_processes

            if assigned_index == current_index:
                allocated_members.append(member)

        self.logger.info(f"进程 {os.getpid()} (索引:{current_index}/{total_processes}) "
                         f"从 {len(members)} 个成员中分配到 {len(allocated_members)} 个")

        return allocated_members

    async def process_single_member_async(self, member: bytes) -> bool:
        """异步处理单个member"""
        try:
            _id = member.decode()

            # JazzCash 监控业务逻辑
            return await self._process_jazzcash_monitor(member)

            # ==================== 原有银行业务逻辑（已注释） ====================
            # 以下代码为原有的银行爬取账单业务逻辑，现已注释
            """
            # 读取缓存，确定是否本地模拟
            payment_mock = self.redis.exists(f"payment_mock:{_id}")
            if payment_mock:
                # 标记本次为本地模拟
                self.local_mock = True

            login_data_str = self.redis.hget(self.hash_key, _id)
            if not login_data_str:
                self.logger.error(f"{self.hash_key} {_id} 不存在数据！从set列表{self.set_key}中删除")
                self.redis.zrem(self.set_key, _id)
                return False

            self.logger.info(f"进程 {os.getpid()} 处理 member[{member}], hash_key: {self.hash_key}")

            # 存在hash数据，则开始登录或者爬取账单等
            self.logger.info(f"{_id},尝试获取锁")
            # 尝试获取锁
            _lock = self.get_lock(_id)
            if not _lock:
                self.logger.warning(f"{_id},未获取到锁！")
                return False

            try:
                self.logger.info(f"{_id}, 获取到锁: {_lock}")

                # 设置当前处理的数据  将数据作为参数传递，而不是依赖实例属性，避免self属性混用
                login_data = simplejson.loads(login_data_str.decode())

                # 获取代理IP
                proxy = self.get_proxies()
                if not proxy:
                    self.logger.error(f"{self.list_key} {_id} 无代理！")
                    return False

                # 检测是否需要换代理
                if 'socks_ip' not in login_data or not login_data['socks_ip']:
                    login_data['socks_ip'] = proxy
                if 'socks_ip' in login_data and login_data['socks_ip']:
                    login_data['socks_ip'] = self.check_proxy(login_data)

                self.logger.info(f"{_id}, hash_key: {self.hash_key}, login_data: {login_data}")

                # 业务逻辑处理
                res = None
                if login_data['status'] == 'grabstatement':
                    res = await self.get_grabstatement(login_data)
                    self.logger.info(f"{login_data['id']}, get_grabstatement() res {type(res)}： {res}")

                # 状态检查
                if login_data['status'] not in ['sendOTP', 'grabOTP', 'device_check', 'send_sms', 'wait_client_send_sms', 'verify_sms', 'grabstatement']:
                    self.logger.error(f"{login_data['id']}, {self.list_key} {_id} status存在问题，舍去！")
                    await self.login_off(login_data)
                    self.read_cache(f'async_main() status error', login_data)
                    return False

                # 处理结果
                if isinstance(res, str) and res == 'logout':
                    self.logger.error(f"{login_data['id']}, {self.list_key} {_id} 登出，删除相关的hash和set中的值")
                    await self.login_off(login_data)
                    self.read_cache(f'async_main() logout', login_data)
                    return False
                else:
                    self.update_key(login_data)
                    # 旧 hash/set 调度已退役；健康检查由 MySQL wallet_status 触发。
                    self.read_cache(f'async_main() True', login_data)
                    return True

            finally:
                # 删除锁
                self.del_lock(_id, _lock)
            """
            # ==================== 原有银行业务逻辑结束 ====================

            # 对于其他银行，暂时返回 True（业务逻辑已注释）
            self.logger.info(f"银行 {self.name} 的爬取业务逻辑已注释，跳过处理 member: {_id}")
            return True

        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(f"process_single_member_async 异步处理成员 {member} 失败: {e} 错误详情：{error_message}")
            return False

    async def _process_jazzcash_monitor(self, member: bytes) -> bool:
        """处理 JazzCash 自动代付监控业务逻辑"""
        _id = member.decode()
        _lock = None

        try:
            # 设置 trace_id
            trace_id_filter.trace_id = f"jazzcash_autopayout_monitor_{os.getpid()}"

            # 获取账号的登录数据
            login_data_str = self.redis.hget(self.hash_key, _id)
            if not login_data_str:
                self.logger.error(f"{self.hash_key} {_id} 不存在数据！从set列表{self.set_key}中删除")
                self.redis.zrem(self.set_key, _id)
                return False

            self.logger.info(f"进程 {os.getpid()} 处理 JazzCash 自动代付监控 member[{member}], hash_key: {self.hash_key}")

            # 尝试获取锁
            self.logger.info(f"{_id}, JazzCash 自动代付监控尝试获取锁")
            _lock = self.get_lock(_id)
            if not _lock:
                self.logger.warning(f"{_id}, JazzCash 自动代付监控未获取到锁！")
                return False

            self.logger.info(f"{_id}, JazzCash 自动代付监控获取到锁: {_lock}")

            # 解析登录数据
            login_data = simplejson.loads(login_data_str.decode())

            # 🔥 新增：重新检查数据库中的status状态，确保账号仍然在线
            payment_id = login_data.get('id', _id)
            if not self.check_payment_status_in_db(payment_id):
                self.logger.warning(f"账号 {_id} (payment_id:{payment_id}) 在数据库中已不在线，清理Redis数据")
                # 从Redis中删除相关数据
                self.redis.hdel(self.hash_key, _id)
                self.redis.zrem(self.set_key, _id)
                self.redis.delete(f'login_on_{self.name}_{_id}')
                return True  # 返回True表示正常清理，不是错误

            # 🔥 新增：检查auto_payout.py的锁状态
            account_id = login_data.get('phone', _id)  # 使用手机号作为account_id
            payment_id = login_data.get('id', _id)     # payment_id

            lock_info = self.check_auto_payout_locks(account_id, payment_id)
            if not lock_info['can_monitor']:
                self.logger.warning(f"账号 {_id} (phone:{account_id}) 被auto_payout.py锁定，跳过监控")
                if lock_info.get('account_locked'):
                    self.logger.info(f"  - 账号锁: {lock_info['lock_details'].get('account_lock', {}).get('value', 'N/A')}")
                if lock_info.get('payment_id_locked'):
                    self.logger.info(f"  - Payment ID锁: {lock_info['lock_details'].get('payment_id_lock', {}).get('value', 'N/A')}")
                return True  # 返回True表示正常跳过，不是错误

            self.logger.info(f"开始执行账号 {_id} 的 JazzCash 自动代付监控检查 (未被auto_payout.py锁定)")

            # 直接使用 login_data 进行监控检查，无需构造额外的 account_info
            # login_data 中已包含所有必要信息：id, status, partner_id, phone 等
            status_info = await self.check_account_health(login_data)

            # 🔥 监控过程中再次检查锁状态（防止监控过程中被锁定）
            lock_info_after = self.check_auto_payout_locks(account_id, payment_id)
            if not lock_info_after['can_monitor']:
                self.logger.warning(f"账号 {_id} 监控期间被auto_payout.py锁定，提前结束监控")
                return True  # 正常退出，避免继续操作可能干扰auto_payout.py

            # 更新Redis缓存（内部会处理501错误删除逻辑）
            account_deleted = await self.update_redis_cache(status_info)
            if account_deleted:
                # 501错误，账号已被删除，停止后续处理
                return True

            # 处理问题账号（主要是日志记录）
            await self.handle_problematic_accounts([status_info])

            # 正常账号处理
            if status_info.get('is_online') and status_info.get('status') == 'online':
                # ✅ 账号正常
                self.on_off(login_data, 1)
                self.update_key(login_data, next_check_interval=300)  # 5分钟后重新检查
                self.logger.info(f"账号 {_id} 监控正常，5分钟后重新检查")
            else:
                # ❌ 账号监控异常（网络错误、API错误等），下线接单
                self.on_off(login_data, 0)
                self.update_key(login_data, next_check_interval=60)   # 1分钟后重新检查 ⚡
                self.logger.warning(f"账号 {_id} 监控异常({status_info.get('status')})，已下线接单，1分钟后重新检查: {status_info.get('error_message')}")

            self.logger.info(f"账号 {_id} 的 JazzCash 自动代付监控检查完成")
            return True

        except Exception as e:
            self.logger.error(f"JazzCash 自动代付监控业务逻辑处理异常: {e}")
            self.logger.error(f"详细错误: {traceback.format_exc()}")
            return False
        finally:
            # 删除锁
            if _lock:
                self.del_lock(_id, _lock)

    async def process_members_concurrent(self, members: List[bytes], concurrent_limit: int = 20):
        """并发处理members"""
        if not members:
            return

        # 创建信号量控制并发数
        semaphore = asyncio.Semaphore(concurrent_limit)

        async def process_with_semaphore(member):
            async with semaphore:
                return await self.process_single_member_async(member)

        # 创建所有任务
        tasks = [process_with_semaphore(member) for member in members]

        # 并发执行
        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        end_time = time.time()

        # 统计结果
        success_count = sum(1 for r in results if r is True)
        error_count = sum(1 for r in results if isinstance(r, Exception))

        self.logger.info(f"进程 {os.getpid()} 并发处理完成: "
                         f"总数 {len(members)}, 成功 {success_count}, 失败 {len(results) - success_count}, "
                         f"异常 {error_count}, 耗时 {end_time - start_time:.2f}秒")

    def main(self):
        try:
            trace_id_filter.trace_id = f"{os.getpid()}_{uuid.uuid4()}"
            if not hasattr(self, '_consistency_check_counter'):
                self._consistency_check_counter = 0
            self._consistency_check_counter += 1
            if self._consistency_check_counter % 10 == 1:
                self.logger.info("执行 JazzCash monitor 数据一致性检查")
                self.check_data_consistency()

            loop = None
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.run_jazzcash_monitor_check())
            except Exception as e:
                self.logger.error(f"JazzCash MySQL monitor 检查异常: {e}")
                self.logger.error(f"详细错误: {traceback.format_exc()}")
            finally:
                if loop and not loop.is_closed():
                    loop.close()

        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            logging.error('main过程错误： 错误详情：{}\n{}'.format(e, error_message))


# 主程序入口
if __name__ == "__main__":
    try:
        logger.info(f"{'=' * 10}JazzCash自动代付监控系统启动{'=' * 10}")
        monitor = AutoPayoutMonitor("jazzcash_monitor")  # 🔥 独立命名，不与auto_payout和EasyPaisa共享
        # 定期输出日志统计（如果使用异步处理器）
        last_stats_time = time.time()

        # 主循环
        while True:
            try:
                monitor.main()

                # 每分钟输出一次日志统计
                current_time = time.time()
                if current_time - last_stats_time >= 60:
                    stats = monitor.get_log_stats()
                    if stats:
                        logger.info(f"日志统计: {stats}")
                    last_stats_time = current_time
            except KeyboardInterrupt:
                logger.info("程序被用户中断")
                break
            except Exception as e:
                tb_str = traceback.format_exc()
                error_message = ''.join(tb_str)
                logger.error('main 循环程序运行错误： 错误详情：{}\n{}'.format(e, error_message))
                # 插入redis，防止非主逻辑内的出错
                monitor.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
            finally:
                time.sleep(2)
    except Exception as e:
        tb_str = traceback.format_exc()
        error_message = ''.join(tb_str)
        logger.error('main 程序启动错误： 错误详情：{}\n{}'.format(e, error_message))
    finally:
        # 确保日志正确关闭
        if hasattr(file_handler, 'close'):
            file_handler.close()
