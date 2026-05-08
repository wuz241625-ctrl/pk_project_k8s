import os
import sys
import time
import uuid
import json
import hashlib
import random
import logging
import asyncio
import traceback
import threading
import secrets
from typing import List
from decimal import Decimal
from datetime import datetime

import aiohttp
import redis
import simplejson

# 将项目的主目录添加进系统path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
parent2_dir = os.path.dirname(parent_dir)
sys.path.insert(0, parent2_dir)

import config
from application.payment_eligibility import can_collect_statement, can_dispatch_df, can_dispatch_ds
from jobs.easypaisa.wallet_status_service import WorkerWalletStatusService
from jobs.easypaisa.common import ProgramLogger, TraceIDFilter
from jobs.easypaisa.common.logging_setup import setup_high_performance_logging

# 程序名称（用于日志）
PROGRAM_NAME = 'easypaisa_monitor'

# 注册自定义日志记录器
logging.setLoggerClass(ProgramLogger)

# 初始化日志系统
logger, trace_id_filter, file_handler = setup_high_performance_logging(
    program_name=PROGRAM_NAME, use_async=True
)

conf = config.get_config()

# 配置参数
API_SERVER_DOMAIN = getattr(conf, 'ospay_api_host', 'http://localhost:8080')

def get_monitor_loop_interval(config, default=30):
    """解析 monitor 外层轮询间隔，最小 1 秒。"""
    try:
        return max(1, int(config.get('easypaisa_monitor_loop_interval', default)))
    except Exception:
        return default

class AutoPayoutMonitor:
    def __init__(self, name):
        self.name = name
        self.lock_time = 30
        self.domain = API_SERVER_DOMAIN
        self.logger = logger
        self.log_handler = file_handler
        self.loop_interval = get_monitor_loop_interval(conf)

        # 默认检查间隔配置（5分钟）
        self.check_interval = 300

        # EasyPaisa 特定配置
        self._init_easypaisa_config()

        # 连接redis
        self.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')

    def _init_easypaisa_config(self):
        """初始化 EasyPaisa 自动代付监控特定配置"""
        self.balance_cache_ttl = 300
        self.limits_cache_ttl = 300

        # EasyPaisa API配置
        self.api_url = conf.get('easypaisa_api_url', 'http://34.150.42.92:83')
        self.user_id = conf.get('easypaisa_user_id', 'ba08c3c0e4f546ad92dd2c2e8542ca36')
        self.secret_key = conf.get('easypaisa_secret_key', 'ca45b35e132b46b9b68dd55f1ab077de')

        # payment_id到phone的缓存
        self.payment_phone_cache = {}
        self.cache_ttl = 300
        self.cache_timestamps = {}

        # Redis键名配置
        self.REDIS_KEYS = {
            'easypaisa_balance_sorted_set': 'easypaisa_balance_sorted',
            'easypaisa_monitor_report': 'easypaisa_monitor_report',
            'easypaisa_limits_hash': 'easypaisa_limits_hash',
            'easypaisa_account_lock_prefix': 'easypaisa_account_lock:',
            'payment_id_lock_prefix': 'payment_id_lock:',
        }

    # ==================== Lock checking ====================

    def check_auto_payout_locks(self, account_id: str, payment_id: str) -> dict:
        """检查账号是否被auto_payout.py锁定"""
        try:
            lock_info = {
                'account_locked': False,
                'payment_id_locked': False,
                'can_monitor': True,
                'lock_details': {}
            }

            account_lock_key = f"{self.REDIS_KEYS['easypaisa_account_lock_prefix']}{account_id}"
            account_lock_value = self.redis.get(account_lock_key)
            if account_lock_value:
                lock_info['account_locked'] = True
                lock_info['can_monitor'] = False
                lock_info['lock_details']['account_lock'] = {
                    'key': account_lock_key,
                    'value': account_lock_value.decode() if account_lock_value else None,
                    'ttl': self.redis.ttl(account_lock_key)
                }

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

            return lock_info

        except Exception as e:
            self.logger.error(f"检查auto_payout.py锁失败: {e}")
            return {'account_locked': False, 'payment_id_locked': False, 'can_monitor': False, 'error': str(e)}

    # ==================== DB queries ====================

    async def get_online_payments_from_db(self):
        """从数据库获取在线状态的payment账号"""
        import pymysql

        try:
            connection = pymysql.connect(
                host=conf['mysql_host'], user=conf['mysql_user'],
                password=conf['mysql_password'], db=conf['mysql_database'],
                charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
            )
            try:
                with connection.cursor() as cur:
                    sql = """
                        SELECT id, phone, account, name, bank_type, bank_type_id, partner_id, wallet_status,
                               collection_status, payout_status, status, certified, manual_status,
                               account_accno, account_iban, channel
                        FROM payment
                        WHERE wallet_status = 1
                          AND (bank_type = 97 OR bank_type_id = 97)
                        ORDER BY id
                    """
                    cur.execute(sql)
                    results = cur.fetchall()
                    self.logger.info(f"从数据库获取到 {len(results)} 个在线payment账号")
                    return results
            finally:
                connection.close()
        except Exception as e:
            self.logger.error(f"从数据库获取payment账号失败: {e}")
            return []

    def get_phone_by_payment_id(self, payment_id):
        """通过payment_id查询手机号和相关信息"""
        import pymysql

        try:
            connection = pymysql.connect(
                host=conf['mysql_host'], user=conf['mysql_user'],
                password=conf['mysql_password'], db=conf['mysql_database'],
                charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
            )
            try:
                with connection.cursor() as cur:
                    sql = """
                        SELECT phone, account, name, bank_type, bank_type_id, partner_id, status, certified,
                               account_accno, account_iban, channel
                        FROM payment
                        WHERE id = %s
                    """
                    cur.execute(sql, payment_id)
                    result = cur.fetchone()
                    if result:
                        return result
                    else:
                        self.logger.warning(f"payment_id {payment_id} 在数据库中不存在")
                        return None
            finally:
                connection.close()
        except Exception as e:
            self.logger.error(f"查询payment_id {payment_id} 失败: {e}")
            return None

    def get_phone_by_payment_id_cached(self, payment_id):
        """带缓存的payment_id查询方法"""
        current_time = time.time()
        cache_key = str(payment_id)

        if cache_key in self.payment_phone_cache:
            if cache_key in self.cache_timestamps:
                cache_age = current_time - self.cache_timestamps[cache_key]
                if cache_age < self.cache_ttl:
                    return self.payment_phone_cache[cache_key]

        payment_info = self.get_phone_by_payment_id(payment_id)
        if payment_info:
            self.payment_phone_cache[cache_key] = payment_info
            self.cache_timestamps[cache_key] = current_time
            # 清理过期缓存
            expired_keys = [k for k, ts in self.cache_timestamps.items() if current_time - ts >= self.cache_ttl]
            for k in expired_keys:
                self.payment_phone_cache.pop(k, None)
                self.cache_timestamps.pop(k, None)

        return payment_info

    def check_payment_status_in_db(self, payment_id):
        """检查 payment 是否存在且可保留采集。"""
        import pymysql

        try:
            connection = pymysql.connect(
                host=conf['mysql_host'], user=conf['mysql_user'],
                password=conf['mysql_password'], db=conf['mysql_database'],
                charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
            )
            try:
                with connection.cursor() as cur:
                    cur.execute("SELECT wallet_status, account_accno FROM payment WHERE id = %s", payment_id)
                    result = cur.fetchone()
                    if result:
                        return can_collect_statement(result)
                    else:
                        self.logger.warning(f"payment_id {payment_id} 在数据库中不存在")
                        return False
            finally:
                connection.close()
        except Exception as e:
            self.logger.error(f"检查payment_id {payment_id} 数据库状态失败: {e}")
            return False

    def should_enable_collection(self, payment_id, payment_data=None):
        """判断是否允许采集账单/余额/限额。"""
        if isinstance(payment_data, dict):
            wallet_status = payment_data.get('wallet_status')
            if wallet_status is not None:
                return can_collect_statement(payment_data)
        return self.check_payment_status_in_db(payment_id)

    def check_payment_ds_order_in_db(self, payment_id):
        """检查 payment 是否仍允许代收派单。"""
        import pymysql
        try:
            connection = pymysql.connect(
                host=conf['mysql_host'], user=conf['mysql_user'],
                password=conf['mysql_password'], db=conf['mysql_database'],
                charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
            )
            try:
                with connection.cursor() as cur:
                    cur.execute(
                        "SELECT wallet_status, account_accno, collection_status, status, certified, manual_status FROM payment WHERE id = %s",
                        payment_id,
                    )
                    result = cur.fetchone()
                    if not result:
                        return False
                    return can_dispatch_ds(result)
            finally:
                connection.close()
        except Exception as e:
            self.logger.error(f"检查payment_id {payment_id} 代收派单资格失败: {e}")
            return False

    def should_enable_ds_order(self, payment_id, payment_data=None):
        if isinstance(payment_data, dict):
            collection_status = payment_data.get('collection_status')
            if collection_status is not None:
                try:
                    return int(collection_status) == 1
                except Exception:
                    pass
        return self.check_payment_ds_order_in_db(payment_id)

    def check_payment_df_order_in_db(self, payment_id):
        """检查 payment 是否仍允许代付派单。"""
        import pymysql
        try:
            connection = pymysql.connect(
                host=conf['mysql_host'], user=conf['mysql_user'],
                password=conf['mysql_password'], db=conf['mysql_database'],
                charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
            )
            try:
                with connection.cursor() as cur:
                    cur.execute(
                        "SELECT wallet_status, account_accno, payout_status, status, certified FROM payment WHERE id = %s",
                        payment_id,
                    )
                    result = cur.fetchone()
                    if not result:
                        return False
                    return can_dispatch_df(result)
            finally:
                connection.close()
        except Exception as e:
            self.logger.error(f"检查payment_id {payment_id} 代付派单资格失败: {e}")
            return False

    def should_enable_df_order(self, payment_id, payment_data=None):
        if isinstance(payment_data, dict):
            payout_status = payment_data.get('payout_status')
            if payout_status is not None:
                try:
                    return int(payout_status) == 1
                except Exception:
                    pass
        return self.check_payment_df_order_in_db(payment_id)

    def should_enable_collection_dispatch(self, payment_id, payment_data=None):
        return self.should_enable_ds_order(payment_id, payment_data)

    # ==================== Health circuit breaking ====================

    def pause_payment_dispatch_for_health_error(self, payment_id, reason="api_error"):
        """健康异常暂停派单必须落 MySQL 最终态。"""
        db_connection = getattr(self, "db_connection", None)
        if not db_connection or not getattr(db_connection, "open", False):
            check_db_connection = getattr(self, "check_db_connection", None)
            if not callable(check_db_connection):
                return 0
            self.db_connection = check_db_connection()
            if not self.db_connection:
                return 0
        with self.db_connection.cursor() as cur:
            try:
                affected = cur.execute(
                    """
                    UPDATE payment
                    SET collection_status = 0, payout_status = 0
                    WHERE id = %s
                      AND (bank_type = 97 OR bank_type = '97' OR bank_type_id = 97)
                      AND (collection_status <> 0 OR payout_status <> 0)
                    """,
                    (payment_id,),
                )
                self.db_connection.commit()
                self.logger.info("EasyPaisa 健康异常暂停最终派单态: payment_id=%s affected=%s reason=%s", payment_id, affected, reason)
                return affected
            except Exception as e:
                self.db_connection.rollback()
                self.logger.error(f"暂停 EasyPaisa 最终派单态失败 payment_id={payment_id}: {e}", exc_info=True)
                return 0

    def restore_payment_dispatch_after_health_success(self, payment_id):
        """健康恢复后按 MySQL 配置字段恢复最终派单态。"""
        db_connection = getattr(self, "db_connection", None)
        if not db_connection or not getattr(db_connection, "open", False):
            check_db_connection = getattr(self, "check_db_connection", None)
            if not callable(check_db_connection):
                return 0
            self.db_connection = check_db_connection()
            if not self.db_connection:
                return 0
        with self.db_connection.cursor() as cur:
            try:
                affected = cur.execute(
                    """
                    UPDATE payment
                    SET collection_status = CASE
                            WHEN wallet_status = 1 AND status = 1 AND certified = 1 AND manual_status = 0 THEN 1
                            ELSE 0
                        END,
                        payout_status = CASE
                            WHEN wallet_status = 1 AND status = 1 AND certified = 1 THEN 1
                            ELSE 0
                        END
                    WHERE id = %s
                      AND (bank_type = 97 OR bank_type = '97' OR bank_type_id = 97)
                    """,
                    (payment_id,),
                )
                self.db_connection.commit()
                self.logger.info("EasyPaisa 健康恢复重算最终派单态: payment_id=%s affected=%s", payment_id, affected)
                return affected
            except Exception as e:
                self.db_connection.rollback()
                self.logger.error(f"恢复 EasyPaisa 最终派单态失败 payment_id={payment_id}: {e}", exc_info=True)
                return 0

    # ==================== Channel helpers ====================

    @staticmethod
    def _channel_value(channel):
        text = str(channel).strip()
        return int(text) if text.isdigit() else text

    @staticmethod
    def _channel_source(payment_data):
        if not isinstance(payment_data, dict):
            return None
        return payment_data.get('channels') or payment_data.get('qr_channel') or payment_data.get('channel')

    def resolve_payment_channels(self, payment_data=None):
        return self.normalize_channels(self._channel_source(payment_data))

    @staticmethod
    def normalize_channels(channels):
        if channels in (None, "", []):
            return []
        raw_items = list(channels) if isinstance(channels, (list, tuple, set)) else [channels]
        normalized = []
        seen = set()
        for item in raw_items:
            if isinstance(item, bytes):
                item = item.decode("utf-8")
            for part in str(item).split(","):
                text = part.strip()
                if not text or text in seen:
                    continue
                seen.add(text)
                normalized.append(text)
        return normalized

    def resolve_cleanup_channels(self, payment_id=None, payment_data=None):
        channels = self.resolve_payment_channels(payment_data)
        if channels:
            return channels
        return ["1001", "1010"]

    # ==================== API calls ====================

    async def check_account_health(self, login_data):
        """检查单个账号的健康状态"""
        payment_id = login_data['id']

        payment_info = self.get_phone_by_payment_id_cached(payment_id)
        if not payment_info or not payment_info.get('phone'):
            return {
                'account_id': payment_id, 'account_name': f"EasyPaisa_{payment_id}",
                'phone': 'UNKNOWN', 'easypaisa_id': payment_id,
                'check_time': datetime.now().isoformat(), 'is_online': False,
                'balance': Decimal('0.00'), 'status': 'phone_not_found',
                'error_message': f'无法获取payment_id {payment_id} 的手机号信息',
                'api_response_time': 0
            }

        phone = payment_info['phone']
        account_name = f"EasyPaisa_{phone}"

        try:
            status_info = {
                'account_id': payment_id, 'account_name': account_name,
                'phone': phone, 'easypaisa_id': phone, 'payment_id': payment_id,
                'check_time': datetime.now().isoformat(), 'is_online': False,
                'balance': Decimal('0.00'), 'status': 'offline',
                'error_message': None, 'api_response_time': 0
            }

            # Balance query with retries
            max_retries = 4
            retry_delay = 1
            api_result = None
            for attempt in range(max_retries):
                try:
                    api_result = await self.call_easypaisa_balance_api(login_data)
                    if api_result and api_result.get('should_retry') and attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        continue
                    break
                except Exception as e:
                    api_result = {'success': False, 'error': str(e)}
                    break

            # Limits query with retries
            limits_result = None
            for attempt in range(max_retries):
                try:
                    limits_result = await self.call_easypaisa_limits_api(login_data)
                    if limits_result and limits_result.get('should_retry') and attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        continue
                    break
                except Exception as e:
                    limits_result = {'success': False, 'error': str(e)}
                    break

            # Process balance result
            if api_result and api_result.get('success'):
                status_info.update({
                    'is_online': True, 'balance': Decimal(str(api_result.get('balance', 0))),
                    'status': 'online', 'api_response_time': api_result.get('response_time', 0)
                })
            elif api_result and api_result.get('should_offline'):
                status_info.update({
                    'is_online': False, 'status': 'account_invalid',
                    'error_message': api_result.get('error', '账号无效(501)'),
                    'api_response_time': api_result.get('response_time', 0), 'force_offline': True
                })
            else:
                status_info.update({
                    'is_online': False, 'status': 'api_error',
                    'error_message': api_result.get('error', 'API调用失败') if api_result else 'API无响应',
                    'api_response_time': api_result.get('response_time', 0) if api_result else 0
                })

            # Process limits result
            if limits_result and limits_result.get('success'):
                limits_data = limits_result.get('limits', {})
                limits_data['phone'] = phone
                limits_data['query_time'] = datetime.now().isoformat()
                limits_data['response_time'] = limits_result.get('response_time', 0)
                await self.save_limits_to_redis(payment_id, limits_data)
            elif limits_result and limits_result.get('should_offline'):
                status_info.update({
                    'is_online': False, 'status': 'account_invalid',
                    'error_message': limits_result.get('error', '账号无效(501)'),
                    'api_response_time': limits_result.get('response_time', status_info.get('api_response_time', 0)),
                    'force_offline': True,
                })

            return status_info

        except Exception as e:
            self.logger.error(f"检查账号 payment_id:{payment_id} 健康状态异常: {e}")
            return {
                'account_id': payment_id, 'account_name': account_name,
                'check_time': datetime.now().isoformat(), 'is_online': False,
                'balance': Decimal('0.00'), 'status': 'check_error',
                'error_message': str(e), 'api_response_time': 0
            }

    async def call_easypaisa_balance_api(self, login_data):
        """调用EasyPaisa余额查询API"""
        import base64

        try:
            payment_id = login_data['id']
            payment_info = self.get_phone_by_payment_id_cached(payment_id)
            if not payment_info or not payment_info.get('phone'):
                return {'success': False, 'error': f'无法获取payment_id {payment_id} 的手机号信息', 'response_time': 0}

            phone = payment_info['phone']
            account_accno = payment_info.get('account_accno')
            if not account_accno:
                return {'success': False, 'error': f'payment_id {payment_id} 缺少account_accno字段', 'response_time': 0}

            payload_data = {"account_id": phone, "accno": account_accno}
            inner_payload = {"id": str(uuid.uuid4()), "action": "queryBalance", "payload": payload_data}

            data_b64 = base64.b64encode(json.dumps(inner_payload).encode()).decode()
            sign = hashlib.md5((data_b64 + self.secret_key).encode()).hexdigest()
            form_data = {'user_id': self.user_id, 'data': data_b64, 'sign': sign}

            start_time = time.time()
            result = await self._post_easypaisa_api(form_data, login_data)
            response_time = time.time() - start_time

            if result is None:
                return {'success': False, 'error': 'API无响应', 'response_time': response_time}

            if result.get('code') == 200:
                data = result.get('data', {})
                body = data.get('body', {}) if isinstance(data, dict) else {}
                balance = body.get('totalbalance', result.get('totalbalance', result.get('balance', 0)))
                return {'success': True, 'balance': balance, 'response_time': response_time, 'data': result}
            elif result.get('code') == 501:
                return {'success': False, 'error': result.get('msg', '账号无效(501)'), 'response_time': response_time, 'data': result, 'should_offline': True}
            elif result.get('code') == 423:
                return {'success': False, 'error': result.get('msg', '服务器忙(423)'), 'response_time': response_time, 'data': result, 'should_retry': True}
            else:
                return {'success': False, 'error': result.get('msg', 'API返回错误'), 'response_time': response_time, 'data': result}

        except Exception as e:
            self.logger.error(f"调用EasyPaisa余额API异常: {e}")
            return {'success': False, 'error': str(e), 'response_time': 0}

    async def call_easypaisa_limits_api(self, login_data):
        """调用EasyPaisa限额查询API"""
        import base64

        try:
            payment_id = login_data['id']
            payment_info = self.get_phone_by_payment_id_cached(payment_id)
            if not payment_info or not payment_info.get('phone'):
                return {'success': False, 'error': f'无法获取payment_id {payment_id} 的手机号信息', 'response_time': 0}

            phone = payment_info['phone']
            payload_data = {"account_id": phone}
            inner_payload = {"id": str(uuid.uuid4()), "action": "queryLimits", "payload": payload_data}

            data_b64 = base64.b64encode(json.dumps(inner_payload).encode()).decode()
            sign = hashlib.md5((data_b64 + self.secret_key).encode()).hexdigest()
            form_data = {'user_id': self.user_id, 'data': data_b64, 'sign': sign}

            start_time = time.time()
            result = await self._post_easypaisa_api(form_data, login_data)
            response_time = time.time() - start_time

            if result is None:
                return {'success': False, 'error': 'API无响应', 'response_time': response_time}

            if result.get('code') == 200:
                data = result.get('data', {})
                body = data.get('body', {}) if isinstance(data, dict) else {}
                limits_info = {
                    'creditDaily': body.get('creditDaily', '0'), 'creditMonthly': body.get('creditMonthly', '0'),
                    'creditYearly': body.get('creditYearly', '0'), 'debitDaily': body.get('debitDaily', '0'),
                    'debitMonthly': body.get('debitMonthly', '0'), 'debitYearly': body.get('debitYearly', '0'),
                    'creditDailyThreshold': body.get('creditDailyThreshold', '0'),
                    'creditMonthlyThreshold': body.get('creditMonthlyThreshold', '0'),
                    'creditYearlyThreshold': body.get('creditYearlyThreshold', '0'),
                    'debitDailyThreshold': body.get('debitDailyThreshold', '0'),
                    'debitMonthlyThreshold': body.get('debitMonthlyThreshold', '0'),
                    'debitYearlyThreshold': body.get('debitYearlyThreshold', '0'),
                }
                return {'success': True, 'limits': limits_info, 'response_time': response_time, 'data': result}
            elif result.get('code') == 501:
                return {'success': False, 'error': result.get('msg', '账号无效(501)'), 'response_time': response_time, 'data': result, 'should_offline': True}
            elif result.get('code') == 423:
                return {'success': False, 'error': result.get('msg', '服务器忙(423)'), 'response_time': response_time, 'data': result, 'should_retry': True}
            else:
                return {'success': False, 'error': result.get('msg', 'API返回错误'), 'response_time': response_time, 'data': result}

        except Exception as e:
            self.logger.error(f"调用EasyPaisa限额API异常: {e}")
            return {'success': False, 'error': str(e), 'response_time': 0}

    async def _post_easypaisa_api(self, form_data, login_data):
        """直接用 aiohttp POST EasyPaisa API，失败重试一次"""
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

    # ==================== Redis cache ====================

    async def update_redis_cache(self, status_info):
        """更新Redis缓存 - 只写 easypaisa_balance_sorted"""
        try:
            account_id = status_info['account_id']
            payment_id = str(status_info.get('payment_id') or account_id)
            account_lock_id = str(status_info.get('phone') or account_id)
            balance_sorted_set = self.REDIS_KEYS['easypaisa_balance_sorted_set']

            if status_info['is_online'] and status_info['status'] == 'online':
                lock_info = self.check_auto_payout_locks(account_lock_id, payment_id)
                if not lock_info.get('can_monitor', False):
                    self.logger.info(
                        "EasyPaisa monitor 跳过余额缓存更新: payment_id=%s account_lock_id=%s lock_info=%s",
                        payment_id,
                        account_lock_id,
                        lock_info,
                    )
                    return False
                balance = float(status_info['balance'])
                self.restore_payment_dispatch_after_health_success(account_id)
                self.redis.zadd(balance_sorted_set, {account_id: balance})
            else:
                if status_info.get('force_offline'):
                    error_msg = status_info.get('error_message', '501账号无效')
                    self.logger.warning(f"账号 {account_id} 因501错误被强制下线: {error_msg}")
                    self.remove_account_completely(account_id, f"501账号无效: {error_msg}")
                    return True
                elif status_info['status'] == 'api_error':
                    self.pause_payment_dispatch_for_health_error(account_id, status_info.get('error_message') or 'api_error')
                else:
                    self.pause_payment_dispatch_for_health_error(account_id, status_info.get('status') or 'health_error')

            return False
        except Exception as e:
            self.logger.error(f"更新账号 {status_info.get('account_id')} Redis缓存失败: {e}")
            return False

    async def save_limits_to_redis(self, payment_id, limits_data):
        """保存限额数据到Redis Hash"""
        try:
            limits_hash_key = self.REDIS_KEYS['easypaisa_limits_hash']
            limits_record = {
                'payment_id': str(payment_id), 'phone': limits_data.get('phone', ''),
                'creditDaily': limits_data.get('creditDaily', '0'), 'creditMonthly': limits_data.get('creditMonthly', '0'),
                'creditYearly': limits_data.get('creditYearly', '0'), 'debitDaily': limits_data.get('debitDaily', '0'),
                'debitMonthly': limits_data.get('debitMonthly', '0'), 'debitYearly': limits_data.get('debitYearly', '0'),
                'creditDailyThreshold': limits_data.get('creditDailyThreshold', '0'),
                'creditMonthlyThreshold': limits_data.get('creditMonthlyThreshold', '0'),
                'creditYearlyThreshold': limits_data.get('creditYearlyThreshold', '0'),
                'debitDailyThreshold': limits_data.get('debitDailyThreshold', '0'),
                'debitMonthlyThreshold': limits_data.get('debitMonthlyThreshold', '0'),
                'debitYearlyThreshold': limits_data.get('debitYearlyThreshold', '0'),
                'query_time': limits_data.get('query_time', datetime.now().isoformat()),
                'update_time': datetime.now().isoformat(),
                'response_time': limits_data.get('response_time', 0)
            }
            self.redis.hset(limits_hash_key, str(payment_id), json.dumps(limits_record))
            return True
        except Exception as e:
            self.logger.error(f"保存限额数据到Redis失败: payment_id={payment_id}, error={e}")
            return False

    def get_limits_from_redis(self, payment_id):
        """从Redis获取指定账号的限额数据"""
        try:
            limits_json = self.redis.hget(self.REDIS_KEYS['easypaisa_limits_hash'], str(payment_id))
            if limits_json:
                if isinstance(limits_json, bytes):
                    limits_json = limits_json.decode('utf-8')
                return json.loads(limits_json)
            return None
        except Exception as e:
            self.logger.error(f"从Redis获取限额数据失败: payment_id={payment_id}, error={e}")
            return None

    def get_all_limits_from_redis(self):
        """从Redis获取所有账号的限额数据"""
        try:
            all_limits = self.redis.hgetall(self.REDIS_KEYS['easypaisa_limits_hash'])
            if not all_limits:
                return {}
            result = {}
            for pid, limits_json in all_limits.items():
                try:
                    if isinstance(pid, bytes):
                        pid = pid.decode('utf-8')
                    if isinstance(limits_json, bytes):
                        limits_json = limits_json.decode('utf-8')
                    result[pid] = json.loads(limits_json)
                except Exception:
                    continue
            return result
        except Exception as e:
            self.logger.error(f"从Redis获取所有限额数据失败: {e}")
            return {}

    # ==================== Account management ====================

    def remove_account_completely(self, payment_id, reason=""):
        """501 处理：标记钱包无效 + 从余额缓存移除"""
        self.logger.warning(f"payment_id {payment_id} 账号无效，执行完全移除: {reason}")
        try:
            self.update_payment_status_to_offline(payment_id, reason)
        except Exception as e:
            self.logger.error(f"更新数据库payment表状态失败: {e}")
        self.redis.zrem(self.REDIS_KEYS['easypaisa_balance_sorted_set'], str(payment_id))
        self.redis.hdel(self.REDIS_KEYS['easypaisa_limits_hash'], str(payment_id))

    def update_payment_status_to_offline(self, account_id, reason="下线"):
        """更新payment表中账号状态为下线"""
        import pymysql
        try:
            connection = pymysql.connect(
                host=conf['mysql_host'], user=conf['mysql_user'],
                password=conf['mysql_password'], db=conf['mysql_database'],
                charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
            )
            try:
                service = WorkerWalletStatusService(connection, self.logger, redis_client=self.redis)
                affected_rows = service.mark_offline(account_id, reason)
                if affected_rows > 0:
                    self.logger.info(f"已将payment表中账号 {account_id} 状态更新为下线，原因: {reason}")
                return affected_rows > 0
            finally:
                connection.close()
        except Exception as e:
            self.logger.error(f"更新payment表账号 {account_id} 状态失败: {e}")
            return False


    # ==================== Process sharding ====================

    def get_active_processes_count(self):
        """获取当前活跃进程数量"""
        try:
            process_key = f"active_processes_{self.name}_monitor"
            current_process_id = f"{process_key}:{os.getpid()}"
            self.redis.setex(current_process_id, 30, int(time.time()))
            active_processes = self.redis.keys(f"{process_key}:*")
            pids = sorted([int(key.decode().split(':')[-1]) for key in active_processes if key.decode().split(':')[-1].isdigit()])
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
        allocated_members = []
        for member in members:
            member_id = member.decode()
            hash_value = int(hashlib.md5(member_id.encode()).hexdigest(), 16)
            if hash_value % total_processes == current_index:
                allocated_members.append(member)
        self.logger.info(f"进程 {os.getpid()} (索引:{current_index}/{total_processes}) 从 {len(members)} 个成员中分配到 {len(allocated_members)} 个")
        return allocated_members

    # ==================== Monitor report ====================

    async def handle_problematic_accounts(self, all_status):
        """处理有问题的账号"""
        try:
            offline_accounts = [s for s in all_status if not s['is_online']]
            invalid_accounts = [s for s in all_status if s['status'] == 'account_invalid']
            if offline_accounts:
                self.logger.warning(f"发现 {len(offline_accounts)} 个离线账号")
            if invalid_accounts:
                for account in invalid_accounts:
                    self.logger.error(f"账号 {account['account_name']} 收到501错误已强制下线: {account['error_message']}")
        except Exception as e:
            self.logger.error(f"处理问题账号异常: {e}")

    async def generate_monitor_report(self, all_status):
        """生成监控报告"""
        try:
            total_count = len(all_status)
            online_count = len([s for s in all_status if s['is_online']])
            total_balance = sum(s['balance'] for s in all_status)
            avg_response_time = sum(s['api_response_time'] for s in all_status) / total_count if total_count > 0 else 0

            report = {
                'report_time': datetime.now().isoformat(),
                'total_accounts': total_count, 'online_accounts': online_count,
                'offline_accounts': total_count - online_count,
                'online_rate': f"{online_count/total_count*100:.1f}%" if total_count > 0 else "0%",
                'total_balance': str(total_balance), 'avg_response_time': f"{avg_response_time:.2f}s"
            }
            report_key = self.REDIS_KEYS['easypaisa_monitor_report']
            self.redis.hmset(report_key, report)
            self.redis.expire(report_key, 3600)
            self.logger.info(f"监控报告: 总={total_count}, 在线={online_count}, 余额={total_balance}")
            return report
        except Exception as e:
            self.logger.error(f"生成监控报告异常: {e}")
            return {}

    # ==================== Main monitoring loop ====================

    async def run_easypaisa_monitor_check(self):
        """执行 EasyPaisa 监控检查（从DB获取在线账号直接检查）"""
        try:
            accounts = await self.get_online_payments_from_db()
            if not accounts:
                self.logger.info("没有在线EasyPaisa账号需要检查")
                return

            members = [str(account['id']).encode() for account in accounts if account.get('id') is not None]
            allocated_members = self.get_process_allocated_members(members)
            allocated_ids = {member.decode() for member in allocated_members}
            if not allocated_ids:
                self.logger.info("当前进程没有分配到 EasyPaisa monitor 账号")
                return
            accounts = [account for account in accounts if str(account.get('id')) in allocated_ids]

            check_tasks = [self.check_account_health({'id': a['id']}) for a in accounts]
            all_status = await asyncio.gather(*check_tasks, return_exceptions=True)

            valid_status = [s for s in all_status if not isinstance(s, Exception)]
            for status in valid_status:
                await self.update_redis_cache(status)
            await self.handle_problematic_accounts(valid_status)
            await self.generate_monitor_report(valid_status)
        except Exception as e:
            self.logger.error(f"EasyPaisa账号状态检查异常: {e}")

    def main(self):
        try:
            trace_id_filter.trace_id = f"{os.getpid()}_{uuid.uuid4()}"

            # 从数据库获取在线账号并执行监控
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self.run_easypaisa_monitor_check())
                finally:
                    loop.close()
            except Exception as e:
                self.logger.error(f"监控检查异常: {e}")
                self.logger.error(f"详细错误: {traceback.format_exc()}")

        except Exception as e:
            self.logger.error(f"main过程错误: {e}\n{traceback.format_exc()}")


# 主程序入口
if __name__ == "__main__":
    try:
        logger.info(f"{'=' * 10}EasyPaisa自动代付监控系统启动{'=' * 10}")
        monitor = AutoPayoutMonitor("ep_monitor")

        while True:
            try:
                monitor.main()
            except KeyboardInterrupt:
                logger.info("程序被用户中断")
                break
            except Exception as e:
                logger.error(f"main 循环程序运行错误: {e}\n{traceback.format_exc()}")
                monitor.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
            finally:
                time.sleep(monitor.loop_interval)
    except Exception as e:
        logger.error(f"main 程序启动错误: {e}\n{traceback.format_exc()}")
    finally:
        if hasattr(file_handler, 'close'):
            file_handler.close()
