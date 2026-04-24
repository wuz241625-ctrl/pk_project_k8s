# -*- coding: utf-8 -*-
"""
这是重构后的 check_third_party_orders.py 脚本。
它负责定时检查处于待确认状态的第三方代付订单，并调用对应的处理器进行状态查询和更新。

主要功能包括：
1. 配置日志记录。
2. 通过修改 sys.path 来确保可以从项目根目录导入其他模块。
3. 使用 aiohttp 库进行异步 HTTP 请求，实现纯粹的多协程处理。
4. 查询过去30分钟内所有状态为1的代付订单。
5. 使用 asyncio.gather() 并发处理所有订单，提高效率。
6. 在 finally 块中确保正确关闭数据库和 Redis 连接。
"""
import pymysql
import logging
import asyncio
import sys
import os
import redis
import aiohttp
import json
import decimal
from datetime import datetime, timedelta
from config import get_config
from logging.handlers import TimedRotatingFileHandler
from urllib.parse import urlencode

# 固定域名，可以在开发和生产环境之间切换
# BASE_URL = "http://localhost:9000"
BASE_URL = "http://ospay689.com"


async def marspay_df_handler(order, third_pay_config, logger):
    """
    异步函数：使用 aiohttp 处理 Marspay 订单的所有逻辑，包括查询API、验证数据和发送回调通知。
    """
    order_code = order['code']

    # 1. 查询 Marspay 订单状态
    ret = None
    try:
        data_get = {'api_token': third_pay_config['mer_key'], 'client_id': order_code}
        
        # 使用 aiohttp.ClientSession 发送异步请求
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(third_pay_config['query_url'], params=data_get, timeout=10) as response:
                response.raise_for_status()
                # 检查响应类型，如果不是JSON，则不尝试解析
                if 'application/json' in response.headers.get('Content-Type', ''):
                    ret = await response.json()
                else:
                    logger.error(f"Received non-JSON response from {third_pay_config['query_url']}: {response.headers.get('Content-Type')}")
                    return False

    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        logger.error(f'Marspay - 查询订单 {order_code} 接口超时或错误: {e}')
        return False
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f'Marspay - 查询订单 {order_code} 响应数据解析失败: {ret}, 异常: {e}')
        return False

    if not ret:
        return False

    query_data = ret.get("transaction", {})
    query_status = query_data.get("status", "").lower()
    query_amount_raw = query_data.get("amount", 0)

    # --- 关键修改部分开始 ---
    if isinstance(query_amount_raw, str):
        query_amount_cleaned = query_amount_raw.replace(',', '').replace(' ', '')
    else:
        query_amount_cleaned = query_amount_raw

    try:
        query_amount = decimal.Decimal(query_amount_cleaned)
    except decimal.InvalidOperation:
        logger.error(f"转换金额失败: {query_amount_raw}")
        query_amount = decimal.Decimal(0)
    # --- 关键修改部分结束 ---
    
    query_utr = query_data.get("utr", None)
    logger.info(f"订单 {order['code']} 的查询数据：{query_data}")
    logger.info(f"订单 {order['code']} 的状态：{query_status}")
    logger.info(f"订单 {order['code']} 的金额：{query_amount}")

    # 2. 验证订单金额
    if not decimal.Decimal(str(order['amount'])) == decimal.Decimal(str(query_amount)):
        logger.error(f"Marspay - 订单 {order_code} 金额不一致: 订单金额 {order['amount']} != 查询金额 {query_amount}")
        return False
    
    # 3. 映射并处理状态
    status_mapping = {
        'success': 'success',
        'failure': 'failed',
        'refund failure': 'failed',
    }
    new_status = status_mapping.get(query_status, None)
    logger.info(f"订单 {order['code']} 的new_status：{new_status}")
    
    if new_status is None:
        logger.info(f"订单 {order_code} 的状态 {query_status} 仍为非终态，跳过更新。")
        return False
    
    # 4. 发送回调通知
    if new_status in ["success", "failed"]:
        try:
            # 动态构建 params，只包含非 None 的值
            params = {
                'status': query_status,
                'client_id': order_code,
                'mer_id': third_pay_config['mer_id'],
            }
            # 只有在成功状态下才添加 utr 参数
            if new_status == "success" and query_utr:
                params['utr'] = query_utr
            
            # 使用全局 BASE_URL 拼接回调地址
            callback_url = f"{BASE_URL}/api/df_notice/marspay"
            logger.info(f"订单 {order['code']} 正在发送回调请求: {callback_url}?{urlencode(params)}")

            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                # 发送回调请求，不期望返回JSON
                async with session.get(callback_url, params=params, timeout=10) as response:
                    response.raise_for_status()

            logger.info(f"回调请求成功，订单 {order['code']} 。")
            logger.info(f"订单 {order['code']} 状态已成功更新为 {new_status}。")
            return True
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error(f"发送回调请求失败: {e}")
            return False
    
    return False

# 获取当前脚本的父目录，即 ospay_apinew 目录
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

LOG_FILE = "check_third_party_orders.log"
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
fh = TimedRotatingFileHandler(LOG_FILE, when='MIDNIGHT', interval=1, backupCount=15)
datefmt = '%Y-%m-%d %H:%M:%S'
format_str = '%(asctime)s %(levelname)s %(message)s '
formatter = logging.Formatter(format_str, datefmt)
fh.setFormatter(formatter)
logger.addHandler(fh)

conf = get_config()


def get_third_party_config(connection, third_pay_name):
    """同步函数：从数据库获取第三方支付配置。"""
    sql = 'select id, mer_id, mer_key, notify_ip, query_url, pay_name_zh from third_pay_df where pay_name = %s'
    try:
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(sql, (third_pay_name,))
            return cursor.fetchone()
    except Exception as e:
        logger.exception(f"查询 {third_pay_name} 配置失败: {e}")
        return None

async def process_single_order(order, third_pay_config, logger):
    """异步函数：根据支付类型调用对应的订单处理器。"""
    otherpay_name = order['otherpay']

    handler_mapping = {
        'marspay代付': marspay_df_handler,
    }

    handler_function = handler_mapping.get(otherpay_name)

    if not handler_function:
        logger.error(f"不支持的第三方支付类型: {otherpay_name}，订单 {order['code']}。")
        return False
    
    # 调用第三方的订单处理器，只传递需要的参数
    return await handler_function(order, third_pay_config, logger)

async def run_third_party_check(rds, connection, third_pay_name):
    """异步函数：检查指定第三方的待确认订单，并按批次处理。"""
    logger.info(f"开始执行对 ID 为 {third_pay_name} 的平台的订单检查...")
    
    third_pay_config = get_third_party_config(connection, third_pay_name)
    if not third_pay_config:
        logger.error(f"未找到 ID 为 {third_pay_name} 的支付通道配置。")
        return

    thirty_minutes_ago = datetime.now() - timedelta(minutes=30)
    sql_orders = "SELECT * FROM orders_df WHERE otherpay_id = %s AND status = 1 AND time_accept >= %s"
    
    try:
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(sql_orders, (third_pay_config['id'], thirty_minutes_ago))
            orders_to_check = cursor.fetchall()
    except Exception as e:
        logger.exception(f"查询 ID 为 {third_pay_config['id']} 的订单时发生错误: {e}")
        return

    if not orders_to_check:
        logger.info(f"过去30分钟内没有找到 ID 为 {third_pay_config['id']} 的待确认订单。")
        return

    total_orders = len(orders_to_check)
    batch_size = 10
    
    logger.info(f"找到 {total_orders} 个 ID 为 {third_pay_config['id']} ({third_pay_config['pay_name_zh']}) 的待确认订单，将按 {batch_size} 单一批次处理。")

    for i in range(0, total_orders, batch_size):
        batch = orders_to_check[i:i + batch_size]
        logger.info(f"开始处理第 {i // batch_size + 1} 个批次，包含 {len(batch)} 个订单。")
        
        tasks = [
            process_single_order(order, third_pay_config, logger)
            for order in batch
        ]
        
        await asyncio.gather(*tasks)
        
        # 如果不是最后一个批次，则等待1秒
        if i + batch_size < total_orders:
            await asyncio.sleep(1)
    
    logger.info(f"ID 为 {third_pay_config['id']} ({third_pay_config['pay_name_zh']}) 的订单检查完成。")

async def main_async():
    """异步主函数，负责建立连接和执行检查任务。"""
    logger.info("启动定时订单检查任务...")
    
    connection = None
    rds = None
    
    try:
        third_pays_to_check = ['marspay']
        
        # 建立同步的 pymysql 和 redis 连接，不使用 with 语句
        connection = pymysql.connect(host=conf['mysql_host'],
                                     user=conf['mysql_user'],
                                     password=conf['mysql_password'],
                                     db=conf['mysql_database'],
                                     charset='utf8mb4',
                                     cursorclass=pymysql.cursors.DictCursor)
        
        rds = redis.Redis(host=conf['redis_host'], port=6379, db=0, decode_responses=True)
        
        for pay_name in third_pays_to_check:
            # 直接传递 rds 和 connection 对象
            await run_third_party_check(rds, connection, pay_name)
                
    except pymysql.MySQLError as e:
        logger.exception(f"MySQL 连接错误: {e}")
    except redis.RedisError as e:
        logger.exception(f"Redis 连接错误: {e}")
    except Exception as e:
        logger.exception(f"主函数运行出错: {e}")
    finally:
        # 确保连接在程序结束时被正确关闭
        if rds:
            try:
                rds.close()
            except Exception as e:
                logger.error(f"关闭 Redis 连接时出错: {e}")
        if connection:
            try:
                connection.close()
            except Exception as e:
                logger.error(f"关闭 MySQL 连接时出错: {e}")

if __name__ == '__main__':
    asyncio.run(main_async())
