#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动代付监控API控制器
提供前端监控界面所需的API接口
"""

import json
import traceback
from datetime import datetime, timedelta
from decimal import Decimal
import tornado
from tornado.web import RequestHandler
from aiomysql import DictCursor

from application.base import BaseHandler
from application.message import msg
from application.easypaisa_runtime.reader import EasyPaisaAdminRuntimeReader


async def load_easypaisa_monitor_counts(redis, runtime_reader):
    return {
        "online_accounts": await runtime_reader.online_df_count(),
        "active_accounts": await runtime_reader.active_df_count(),
    }


class AutoPayoutStatsHandler(BaseHandler):
    """自动代付统计数据API"""
    
    async def get(self):
        """获取自动代付统计数据"""
        try:
            # 获取今日和昨日的统计数据
            today = datetime.now().date()
            yesterday = today - timedelta(days=1)
            
            self.logger.info(f"[统计查询] 开始查询统计数据 - 今日: {today}, 昨日: {yesterday}")
            
            # 今日统计 (status=4，完成的)
            today_stats = await self._get_daily_stats(today)
            self.logger.info(f"[统计查询] 今日完成统计结果: 金额={today_stats['amount']}, 笔数={today_stats['count']}")
            
            # 今日所有状态统计 (用于总增长)
            today_all_stats = await self._get_daily_all_stats(today)
            self.logger.info(f"[统计查询] 今日所有状态统计结果: 金额={today_all_stats['amount']}, 笔数={today_all_stats['count']}")
            
            # 昨日统计 (status=4，完成的)
            yesterday_stats = await self._get_daily_stats(yesterday)
            self.logger.info(f"[统计查询] 昨日完成统计结果: 金额={yesterday_stats['amount']}, 笔数={yesterday_stats['count']}")
            
            # 当日总体统计
            total_stats = await self._get_total_stats()
            
            # 当日总成功率统计
            total_success_rate = await self._get_total_success_rate()
            self.logger.info(f"[统计查询] 当日总成功率: {total_success_rate}%")
            
            # 今日成功率统计
            today_success_rate = await self._get_daily_success_rate(today)
            self.logger.info(f"[统计查询] 今日成功率: {today_success_rate}%")
            
            # 昨日成功率统计
            yesterday_success_rate = await self._get_daily_success_rate(yesterday)
            self.logger.info(f"[统计查询] 昨日成功率: {yesterday_success_rate}%")
            
            result = {
                "code": 20000,
                "message": "success",
                "data": {
                    "today": {
                        "amount": float(today_stats['amount']),
                        "count": today_stats['count']
                    },
                    "today_all": {
                        "amount": float(today_all_stats['amount']),
                        "count": today_all_stats['count']
                    },
                    "yesterday": {
                        "amount": float(yesterday_stats['amount']),
                        "count": yesterday_stats['count']
                    },
                    "total": {
                        "amount": float(total_stats['amount']),
                        "count": total_stats['count']
                    },
                    "success_rate": float(total_success_rate),
                    "today_success_rate": float(today_success_rate),
                    "yesterday_success_rate": float(yesterday_success_rate)
                }
            }
            
            self.write(result)
            
        except Exception as e:
            self.logger.error(f"获取自动代付统计数据失败: {str(e)}")
            self.logger.error(traceback.format_exc())
            self.write({
                "code": 500,
                "message": f"系统错误: {str(e)}",
                "data": None
            })
    
    async def _get_daily_stats(self, date):
        """获取指定日期的统计数据"""
        try:
            self.logger.info(f"[日统计] 开始查询日期: {date} 的统计数据")
            
            async with self.application.db.acquire() as conn:
                async with conn.cursor(DictCursor) as cur:
                    # 查询指定日期的自动代付订单统计
                    sql = """
                        SELECT 
                            COALESCE(SUM(amount), 0) as total_amount,
                            COUNT(*) as total_count
                        FROM orders_df 
                        WHERE DATE(time_create) = %s 
                          AND status = 4
                          AND payout_type = 1
                    """
                    
                    self.logger.info(f"[日统计] 执行SQL: {sql.strip()}")
                    self.logger.info(f"[日统计] 查询参数: date={date}")
                    
                    await cur.execute(sql, (date,))
                    result = await cur.fetchone()
                    
                    self.logger.info(f"[日统计] 原始查询结果: {result}")
                  
                    final_result = {
                        'amount': result['total_amount'] or Decimal('0'),
                        'count': result['total_count'] or 0
                    }
                    
                    self.logger.info(f"[日统计] 日期 {date} 最终结果: {final_result}")
                    return final_result
                    
        except Exception as e:
            self.logger.error(f"获取日期 {date} 统计数据失败: {str(e)}")
            self.logger.error(traceback.format_exc())
            return {'amount': Decimal('0'), 'count': 0}
    
    async def _get_daily_all_stats(self, date):
        """获取指定日期所有状态的统计数据"""
        try:
            self.logger.info(f"[日统计-全部] 开始查询日期: {date} 的所有状态统计数据")
            
            async with self.application.db.acquire() as conn:
                async with conn.cursor(DictCursor) as cur:
                    # 查询指定日期的所有自动代付订单统计
                    sql = """
                        SELECT 
                            COALESCE(SUM(amount), 0) as total_amount,
                            COUNT(*) as total_count
                        FROM orders_df 
                        WHERE DATE(time_create) = %s 
                          AND payout_type = 1
                    """
                    
                    self.logger.info(f"[日统计-全部] 执行SQL: {sql.strip()}")
                    self.logger.info(f"[日统计-全部] 查询参数: date={date}")
                    
                    await cur.execute(sql, (date,))
                    result = await cur.fetchone()
                    
                    self.logger.info(f"[日统计-全部] 原始查询结果: {result}")
                    
                    final_result = {
                        'amount': result['total_amount'] or Decimal('0'),
                        'count': result['total_count'] or 0
                    }
                    
                    self.logger.info(f"[日统计-全部] 日期 {date} 最终结果: {final_result}")
                    return final_result
                    
        except Exception as e:
            self.logger.error(f"获取日期 {date} 所有状态统计数据失败: {str(e)}")
            self.logger.error(traceback.format_exc())
            return {'amount': Decimal('0'), 'count': 0}
    
    async def _get_total_stats(self):
        """获取当日总体统计数据"""
        try:
            from datetime import datetime
            today = datetime.now().date()
            
            async with self.application.db.acquire() as conn:
                async with conn.cursor(DictCursor) as cur:
                    # 查询当日所有自动代付订单统计
                    sql = """
                        SELECT 
                            COALESCE(SUM(amount), 0) as total_amount,
                            COUNT(*) as total_count
                        FROM orders_df 
                        WHERE DATE(time_create) = %s
                          AND payout_type = 1
                    """
                    await cur.execute(sql, (today,))
                    result = await cur.fetchone()
                    
                    return {
                        'amount': result['total_amount'] or Decimal('0'),
                        'count': result['total_count'] or 0
                    }
        except Exception as e:
            self.logger.error(f"获取当日总体统计数据失败: {str(e)}")
            return {'amount': Decimal('0'), 'count': 0}
    
    async def _get_success_rate(self):
        """获取成功率"""
        try:
            async with self.application.db.acquire() as conn:
                async with conn.cursor(DictCursor) as cur:
                    # 查询成功率
                    sql = """
                        SELECT 
                            COUNT(CASE WHEN status = 4 THEN 1 END) as success_count,
                            COUNT(*) as total_count
                        FROM orders_df 
                        WHERE payout_type = 1
                          AND time_create >= DATE_SUB(NOW(), INTERVAL 30 DAY)
                    """
                    await cur.execute(sql, ())
                    result = await cur.fetchone()
                    
                    if result['total_count'] > 0:
                        success_rate = (result['success_count'] / result['total_count']) * 100
                        return round(success_rate, 2)  # 保留两位小数
                    return 0.00
                    
        except Exception as e:
            self.logger.error(f"获取成功率失败: {str(e)}")
            return 0.00

    async def _get_total_success_rate(self):
        """获取当日总成功率"""
        try:
            from datetime import datetime
            today = datetime.now().date()
            self.logger.info(f"[总成功率] 开始查询当日成功率: {today}")
            
            async with self.application.db.acquire() as conn:
                async with conn.cursor(DictCursor) as cur:
                    # 查询当日的成功率
                    sql = """
                        SELECT 
                            COUNT(CASE WHEN status = 4 THEN 1 END) as success_count,
                            COUNT(*) as total_count
                        FROM orders_df 
                        WHERE DATE(time_create) = %s
                          AND payout_type = 1
                    """
                    
                    self.logger.info(f"[总成功率] 执行SQL: {sql.strip()}")
                    self.logger.info(f"[总成功率] 查询参数: date={today}")
                    
                    await cur.execute(sql, (today,))
                    result = await cur.fetchone()
                    
                    self.logger.info(f"[总成功率] 原始查询结果: {result}")
                    
                    if result['total_count'] > 0:
                        success_rate = (result['success_count'] / result['total_count']) * 100
                        final_rate = round(success_rate, 2)  # 保留两位小数
                        self.logger.info(f"[总成功率] 当日成功率: {final_rate}%")
                        return final_rate
                    
                    self.logger.info(f"[总成功率] 当日无订单数据，成功率: 0.00%")
                    return 0.00
                    
        except Exception as e:
            self.logger.error(f"获取当日总成功率失败: {str(e)}")
            self.logger.error(traceback.format_exc())
            return 0.00

    async def _get_daily_success_rate(self, date):
        """获取指定日期的成功率"""
        try:
            self.logger.info(f"[日成功率] 开始查询日期: {date} 的成功率")
            
            async with self.application.db.acquire() as conn:
                async with conn.cursor(DictCursor) as cur:
                    # 查询指定日期的成功率
                    sql = """
                        SELECT 
                            COUNT(CASE WHEN status = 4 THEN 1 END) as success_count,
                            COUNT(*) as total_count
                        FROM orders_df 
                        WHERE DATE(time_create) = %s
                          AND payout_type = 1
                    """
                    
                    self.logger.info(f"[日成功率] 执行SQL: {sql.strip()}")
                    self.logger.info(f"[日成功率] 查询参数: date={date}")
                    
                    await cur.execute(sql, (date,))
                    result = await cur.fetchone()
                    
                    self.logger.info(f"[日成功率] 原始查询结果: {result}")
                    
                    if result['total_count'] > 0:
                        success_rate = (result['success_count'] / result['total_count']) * 100
                        final_rate = round(success_rate, 2)  # 保留两位小数
                        self.logger.info(f"[日成功率] 日期 {date} 成功率: {final_rate}%")
                        return final_rate
                    
                    self.logger.info(f"[日成功率] 日期 {date} 无订单数据，成功率: 0.00%")
                    return 0.00
                    
        except Exception as e:
            self.logger.error(f"获取日期 {date} 成功率失败: {str(e)}")
            self.logger.error(traceback.format_exc())
            return 0.00


class AutoPayoutOrdersHandler(BaseHandler):
    """自动代付订单列表API"""
    
    async def get(self):
        """获取自动代付订单列表"""
        try:
            # 获取查询参数
            page = int(self.get_argument('page', 1))
            page_size = int(self.get_argument('page_size', 20))
            order_code = self.get_argument('orderCode', '')
            merchant_id = self.get_argument('merchantId', '')
            start_date = self.get_argument('startDate', '')
            end_date = self.get_argument('endDate', '')
            status = self.get_argument('status', '')
            
            # 调试日志
            self.logger.info(f"查询参数 - orderCode: '{order_code}', merchantId: '{merchant_id}', startDate: '{start_date}', endDate: '{end_date}'")
            
            # 构建查询条件
            where_conditions = ["payout_type = 1"]
            params = []
            
            if order_code:
                where_conditions.append("code = %s")
                params.append(order_code)
            
            if merchant_id:
                where_conditions.append("partner_id = %s")
                params.append(merchant_id)
            
            if start_date:
                where_conditions.append("time_create >= %s")
                params.append(f"{start_date} 00:00:00")
            
            if end_date:
                where_conditions.append("time_create <= %s")
                params.append(f"{end_date} 23:59:59")
            
            if status:
                where_conditions.append("status = %s")
                params.append(int(status))
            
            where_clause = " AND ".join(where_conditions)
            
            # 调试SQL查询
            self.logger.info(f"WHERE条件: {where_clause}")
            self.logger.info(f"查询参数: {params}")
            
            # 查询订单数据
            async with self.application.db.acquire() as conn:
                async with conn.cursor(DictCursor) as cur:
                    # 查询总数
                    count_sql = f"""
                        SELECT COUNT(*) as total 
                        FROM orders_df 
                        WHERE {where_clause}
                    """
                    await cur.execute(count_sql, params)
                    total_result = await cur.fetchone()
                    total = total_result['total']
                    
                    # 查询分页数据
                    offset = (page - 1) * page_size
                    data_sql = f"""
                        SELECT 
                            code,
                            amount,
                            status,
                            payment_id,
                            partner_id,
                            payment_name,
                            remark,
                            time_create,
                            time_accept,
                            time_payed,
                            time_success
                        FROM orders_df 
                        WHERE {where_clause}
                        ORDER BY time_create DESC
                        LIMIT %s OFFSET %s
                    """
                    await cur.execute(data_sql, params + [page_size, offset])
                    orders = await cur.fetchall()
                    
                    # 格式化订单数据
                    order_list = []
                    for order in orders:
                        status_text = self._get_status_text(order['status'])
                        order_list.append({
                            'order_code': order['code'],
                            'amount': float(order['amount']),
                            'status': order['status'],
                            'status_text': status_text,
                            'payment_id': order['payment_id'],
                            'merchant_id': order['partner_id'],
                            'user_name': order['payment_name'],
                            'remarks': order['remark'],
                            'created_time': order['time_create'].strftime('%Y-%m-%d %H:%M:%S') if order['time_create'] else '',
                            'accept_time': order['time_accept'].strftime('%Y-%m-%d %H:%M:%S') if order['time_accept'] else '',
                            'paid_time': order['time_payed'].strftime('%Y-%m-%d %H:%M:%S') if order['time_payed'] else '',
                            'success_time': order['time_success'].strftime('%Y-%m-%d %H:%M:%S') if order['time_success'] else ''
                        })
            
            result = {
                "code": 20000,
                "message": "success",
                "data": {
                    "list": order_list,
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": (total + page_size - 1) // page_size
                }
            }
            
            self.write(result)
            
        except Exception as e:
            self.logger.error(f"获取自动代付订单列表失败: {str(e)}")
            self.logger.error(traceback.format_exc())
            self.write({
                "code": 500,
                "message": f"系统错误: {str(e)}",
                "data": None
            })
    
    def _get_status_text(self, status):
        """获取状态文本"""
        status_map = {
            0: '待处理',
            1: '处理中',
            2: '确认中',
            3: '成功',
            4: '通知商户已到账',
            5: '异常按成功处理',
            -1: '失败'
        }
        return status_map.get(status, '未知')


class AutoPayoutToggleHandler(BaseHandler):
    """自动代付开关控制API"""
    
    async def post(self):
        """切换自动代付开关状态"""
        try:
            data = json.loads(self.request.body)
            enabled = data.get('enabled', False)
            
            # 设置紧急停止状态
            # 开启时：取消紧急停止(设为0)
            # 关闭时：启动紧急停止(设为1)
            await self.application.redis.set("easypaisa_emergency_stop", "0" if enabled else "1")
            
            # 记录操作日志
            action = "开启自动代付(停止紧急停机)" if enabled else "关闭自动代付(启动紧急停机)"
            self.logger.info(f"自动代付开关操作: {action}")
            
            self.write({
                "code": 20000,
                "message": "操作成功",
                "data": {
                    "enabled": enabled,
                    "emergency_stop": not enabled  # 开启时emergency_stop为False，关闭时为True
                }
            })
            
        except Exception as e:
            self.logger.error(f"切换自动代付开关失败: {str(e)}")
            self.logger.error(traceback.format_exc())
            self.write({
                "code": 500,
                "message": f"系统错误: {str(e)}",
                "data": None
            })
    
    async def get(self):
        """获取自动代付开关状态"""
        try:
            emergency_stop = await self.redis.get("easypaisa_emergency_stop")
            # emergency_stop为"0"或None时表示开启，为"1"时表示关闭
            enabled = emergency_stop != "1"
            
            self.write({
                "code": 20000,
                "message": "success",
                "data": {
                    "enabled": enabled
                }
            })
            
        except Exception as e:
            self.logger.error(f"获取自动代付开关状态失败: {str(e)}")
            self.write({
                "code": 500,
                "message": f"系统错误: {str(e)}",
                "data": None
            })


# class AutoPayoutEmergencyStopHandler(BaseHandler):
#     """自动代付紧急停止API - 已禁用，前端按钮已隐藏"""
#     
#     async def post(self):
#         """紧急停止自动代付"""
#         try:
#             # 设置紧急停止标志
#             await self.application.redis.set("easypaisa_emergency_stop", "1")
#             await self.application.redis.set("auto_payout_enabled", "0")
#             
#             # 记录紧急停止日志
#             self.logger.warning("自动代付系统被紧急停止")
#             
#             self.write({
#                 "code": 20000,
#                 "message": "紧急停止成功",
#                 "data": {
#                     "stopped": True
#                 }
#             })
#             
#         except Exception as e:
#             self.logger.error(f"紧急停止失败: {str(e)}")
#             self.logger.error(traceback.format_exc())
#             self.write({
#                 "code": 500,
#                 "message": f"系统错误: {str(e)}",
#                 "data": None
#             })


class AutoPayoutMonitorHandler(BaseHandler):
    """自动代付系统监控API"""
    
    async def get(self):
        """获取自动代付系统监控信息"""
        try:
            # 获取系统状态
            emergency_stop = await self.redis.get("easypaisa_emergency_stop")
            
            runtime_reader = EasyPaisaAdminRuntimeReader(self.redis)
            counts = await load_easypaisa_monitor_counts(self.redis, runtime_reader)
            online_accounts = counts["online_accounts"]
            active_accounts = counts["active_accounts"]
            
            # 获取待处理订单数量
            async with self.db.acquire() as conn:
                async with conn.cursor(DictCursor) as cur:
                    # 待处理订单
                    sql = """
                        SELECT COUNT(*) as pending_count
                        FROM orders_df 
                        WHERE status = 0 
                          AND time_create >= DATE_SUB(NOW(), INTERVAL 3 DAY)
                    """
                    await cur.execute(sql)
                    result = await cur.fetchone()
                    pending_orders = result['pending_count']
                    
                    # 处理中订单
                    sql = """
                        SELECT COUNT(*) as processing_count
                        FROM orders_df 
                        WHERE status = 1 
                          AND payout_type = 1
                    """
                    await cur.execute(sql)
                    result = await cur.fetchone()
                    processing_orders = result['processing_count']
            
            # 获取最近10分钟的处理速度
            recent_processed = await self._get_recent_processed_count()
            
            result = {
                "code": 20000,
                "message": "success",
                "data": {
                    "system_status": {
                        "enabled": emergency_stop != "1",  # emergency_stop为"0"或None时表示开启
                        "emergency_stop": emergency_stop == "1"
                    },
                    "account_status": {
                        "online_count": online_accounts or 0,
                        "active_count": active_accounts or 0
                    },
                    "order_status": {
                        "pending_count": pending_orders,
                        "processing_count": processing_orders,
                        "recent_processed": recent_processed
                    }
                }
            }
            
            self.write(result)
            
        except Exception as e:
            self.logger.error(f"获取监控信息失败: {str(e)}")
            self.logger.error(traceback.format_exc())
            self.write({
                "code": 500,
                "message": f"系统错误: {str(e)}",
                "data": None
            })
    
    async def _get_recent_processed_count(self):
        """获取最近10分钟处理的订单数量"""
        try:
            async with self.application.db.acquire() as conn:
                async with conn.cursor(DictCursor) as cur:
                    sql = """
                        SELECT COUNT(*) as count
                        FROM orders_df 
                        WHERE payout_type = 1
                          AND time_accept >= DATE_SUB(NOW(), INTERVAL 10 MINUTE)
                    """
                    await cur.execute(sql)
                    result = await cur.fetchone()
                    return result['count'] or 0
        except Exception as e:
            self.logger.error(f"获取最近处理数量失败: {str(e)}")
            return 0


class AutoPayoutOrderDetailHandler(BaseHandler):
    """自动代付订单详情及操作日志API"""
    
    async def get(self):
        """获取订单详情和操作日志"""
        try:
            order_code = self.get_argument('orderCode', '')
            
            if not order_code:
                self.write({
                    "code": 400,
                    "message": "订单号不能为空",
                    "data": None
                })
                return
            
            async with self.application.db.acquire() as conn:
                async with conn.cursor(DictCursor) as cur:
                    # 1. 查询订单基本信息
                    order_sql = """
                        SELECT 
                            code, amount, status, payment_id, partner_id,
                            payment_name, remark, time_create, time_accept,
                            time_payed, time_success, merchant_id
                        FROM orders_df 
                        WHERE code = %s AND payout_type = 1
                    """
                    self.logger.info(f"查询订单SQL: {order_sql}")
                    await cur.execute(order_sql, (order_code,))
                    order_info = await cur.fetchone()
                    self.logger.info(f"查询到订单信息: {order_info}")
                    
                    if not order_info:
                        self.write({
                            "code": 404,
                            "message": "订单不存在",
                            "data": None
                        })
                        return
                    
                    # 2. 查询操作日志
                    logs_sql = """
                        SELECT 
                            operation_type, status, amount, currency,
                            from_account_number, to_account_number, to_account_name,
                            transaction_id, reference_number, transfer_type,
                            before_balance, after_balance,
                            error_code, error_message, process_time,
                            created_at, trace_id, retry_count
                        FROM easypaisa_operation_logs 
                        WHERE order_code = %s 
                        ORDER BY created_at DESC
                    """
                    self.logger.info(f"查询操作日志SQL: {logs_sql}")
                    self.logger.info(f"查询订单号: {order_code}")
                    
                    await cur.execute(logs_sql, (order_code,))
                    operation_logs = await cur.fetchall()
                    
                    self.logger.info(f"查询到 {len(operation_logs)} 条操作日志")
                    
                    # 3. 格式化订单数据
                    order_detail = {
                        'order_code': order_info['code'],
                        'amount': float(order_info['amount']),
                        'status': order_info['status'],
                        'payment_id': order_info['payment_id'],
                        'merchant_id': order_info['partner_id'],
                        'user_name': order_info['payment_name'],
                        'remarks': order_info['remark'],
                        'created_time': order_info['time_create'].strftime('%Y-%m-%d %H:%M:%S') if order_info['time_create'] else '',
                        'accept_time': order_info['time_accept'].strftime('%Y-%m-%d %H:%M:%S') if order_info['time_accept'] else '',
                        'paid_time': order_info['time_payed'].strftime('%Y-%m-%d %H:%M:%S') if order_info['time_payed'] else '',
                        'success_time': order_info['time_success'].strftime('%Y-%m-%d %H:%M:%S') if order_info['time_success'] else ''
                    }
                    
                    # 4. 格式化操作日志
                    formatted_logs = []
                    for log in operation_logs:
                        formatted_logs.append({
                            'operation_type': log['operation_type'],
                            'transfer_type': log['transfer_type'],
                            'status': log['status'],
                            'amount': float(log['amount']) if log['amount'] else 0,
                            'currency': log['currency'],
                            'from_account': log['from_account_number'],
                            'to_account': log['to_account_number'],
                            'to_account_name': log['to_account_name'],
                            'transaction_id': log['transaction_id'],
                            'reference_number': log['reference_number'],
                            'before_balance': float(log['before_balance']) if log['before_balance'] is not None else None,
                            'after_balance': float(log['after_balance']) if log['after_balance'] is not None else None,
                            'error_code': log['error_code'],
                            'error_message': log['error_message'],
                            'process_time': float(log['process_time'])/1000 if log['process_time'] else 0,  # 转换为秒
                            'created_at': log['created_at'].strftime('%Y-%m-%d %H:%M:%S') if log['created_at'] else '',
                            'trace_id': log['trace_id'],
                            'retry_count': log['retry_count'] or 0
                        })
            
            result = {
                "code": 20000,
                "message": "success",
                "data": {
                    "order_detail": order_detail,
                    "operation_logs": formatted_logs,
                    "logs_count": len(formatted_logs)
                }
            }
            
            self.write(result)
            
        except Exception as e:
            self.logger.error(f"获取订单详情失败: {str(e)}")
            self.logger.error(traceback.format_exc())
            self.write({
                "code": 500,
                "message": f"系统错误: {str(e)}",
                "data": None
            })


class AutoPayoutPaymentIdCooldownHandler(BaseHandler):
    """Payment ID冷却期配置API"""
    
    async def post(self):
        """设置Payment ID冷却期"""
        try:
            # 记录请求信息
            self.logger.info(f"[冷却期配置] 收到POST请求: {self.request.uri}")
            self.logger.info(f"[冷却期配置] 请求参数: {dict(self.request.arguments)}")
            
            # 优先从URL参数获取，如果没有则从请求体获取
            if self.get_argument('minutes', None) is not None or self.get_argument('seconds', None) is not None:
                # 从URL参数获取
                minutes_raw = self.get_argument('minutes', '0')
                seconds_raw = self.get_argument('seconds', '0')
                self.logger.info(f"[冷却期配置] 从URL参数获取 - minutes: {minutes_raw}, seconds: {seconds_raw}")
            else:
                # 从请求体获取
                if not self.request.body:
                    self.logger.error(f"[冷却期配置] 请求体和URL参数都为空")
                    return await self.json_response(msg[10007])
                    
                data = json.loads(self.request.body)
                self.logger.info(f"[冷却期配置] 从请求体获取JSON数据: {data}")
                minutes_raw = data.get('minutes', 0)
                seconds_raw = data.get('seconds', 0)
                self.logger.info(f"[冷却期配置] 从请求体获取 - minutes: {minutes_raw}, seconds: {seconds_raw}")
            
            # 类型转换
            minutes = int(minutes_raw)
            seconds = int(seconds_raw)
            self.logger.info(f"[冷却期配置] 转换后参数 - minutes: {minutes}, seconds: {seconds}")
            
            # 参数验证 - minutes和seconds都可以为0，但不能为负数，seconds不能>=60
            if minutes < 0:
                self.logger.error(f"[冷却期配置] 参数验证失败: minutes不能小于0，当前值: {minutes}")
                return await self.json_response(msg[10007])
            
            if seconds < 0:
                self.logger.error(f"[冷却期配置] 参数验证失败: seconds不能小于0，当前值: {seconds}")
                return await self.json_response(msg[10007])
                
            if seconds >= 60:
                self.logger.error(f"[冷却期配置] 参数验证失败: seconds不能>=60，当前值: {seconds}")
                return await self.json_response(msg[10007])
            
            # 转换为总秒数
            total_seconds = minutes * 60 + seconds
            
            
            # 存储到Redis
            await self.application.redis.set("easypaisa_paymentid_cooldown_seconds", str(total_seconds))
            
            # 记录操作日志
            self.logger.info(f"Payment ID冷却期配置更新: {minutes}分{seconds}秒 = {total_seconds}秒")
            
            result = dict(
                code=20000,
                data={
                    "minutes": minutes,
                    "seconds": seconds,
                    "total_seconds": total_seconds
                },
                msg="配置成功"
            )
            return await self.json_response(result)
            
        except json.JSONDecodeError as e:
            self.logger.error(f"[冷却期配置] JSON解析失败: {str(e)}")
            self.logger.error(f"[冷却期配置] 请求体内容: {self.request.body}")
            return await self.json_response(msg[10007])
        except ValueError as e:
            self.logger.error(f"[冷却期配置] 参数类型转换失败: {str(e)}")
            return await self.json_response(msg[10007])
        except Exception as e:
            self.logger.error(f"[冷却期配置] 设置Payment ID冷却期失败: {str(e)}")
            self.logger.error(traceback.format_exc())
            return await self.json_response(msg[10007])
    
    async def get(self):
        """获取Payment ID冷却期配置"""
        try:
            self.logger.info(f"[冷却期配置] 开始获取Payment ID冷却期配置")
            
            # 从Redis读取配置
            cooldown_seconds = await self.application.redis.get("easypaisa_paymentid_cooldown_seconds")
            self.logger.info(f"[冷却期配置] 从Redis读取到的值: {cooldown_seconds}")
            
            if cooldown_seconds:
                total_seconds = int(cooldown_seconds)
                self.logger.info(f"[冷却期配置] 使用Redis配置: {total_seconds}秒")
            else:
                total_seconds = 300  # 默认5分钟
                self.logger.info(f"[冷却期配置] 使用默认配置: {total_seconds}秒")
            
            # 转换为分钟和秒
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            self.logger.info(f"[冷却期配置] 转换结果: {minutes}分{seconds}秒")
            
            result = dict(
                code=20000,
                data={
                    "minutes": minutes,
                    "seconds": seconds,
                    "total_seconds": total_seconds
                },
                msg="获取配置成功"
            )
            return await self.json_response(result)
            
        except Exception as e:
            self.logger.error(f"[冷却期配置] 获取Payment ID冷却期配置失败: {str(e)}")
            self.logger.error(traceback.format_exc())
            return await self.json_response(msg[10007])


class AutoPayoutOrderCooldownConfigHandler(BaseHandler):
    """订单冷却期配置API"""
    
    async def post(self):
        """设置订单冷却期配置
        
        请求格式:
        {
            "levels": [
                {"level": 1, "minutes": 30},
                {"level": 2, "minutes": 120},
                {"level": 3, "minutes": 360},
                {"level": 4, "minutes": 1440}
            ]
        }
        """
        try:
            # 记录请求信息
            self.logger.info(f"[订单冷却期配置] 收到POST请求: {self.request.uri}")
            
            # 解析请求体
            if not self.request.body:
                self.logger.error(f"[订单冷却期配置] 请求体为空")
                return await self.json_response(msg[10007])
            
            data = json.loads(self.request.body)
            self.logger.info(f"[订单冷却期配置] 接收到配置数据: {json.dumps(data, ensure_ascii=False)}")
            
            levels = data.get('levels', [])
            
            # ========== 参数验证 ==========
            
            # 1. 必须至少有1个等级
            if not levels or len(levels) == 0:
                self.logger.error(f"[订单冷却期配置] 验证失败: 必须至少配置1个等级")
                return await self.json_response(msg[10007])
            
            # 2. 验证每个等级的数据格式
            for idx, level_config in enumerate(levels):
                if not isinstance(level_config, dict):
                    self.logger.error(f"[订单冷却期配置] 验证失败: 第{idx+1}个等级数据格式错误")
                    return await self.json_response(msg[10007])
                
                if 'level' not in level_config or 'minutes' not in level_config:
                    self.logger.error(f"[订单冷却期配置] 验证失败: 第{idx+1}个等级缺少必要字段")
                    return await self.json_response(msg[10007])
                
                try:
                    level_num = int(level_config['level'])
                    minutes = int(level_config['minutes'])
                except (ValueError, TypeError) as e:
                    self.logger.error(f"[订单冷却期配置] 验证失败: 第{idx+1}个等级数据类型错误: {e}")
                    return await self.json_response(msg[10007])
                
                # 3. level必须从1开始且连续
                if level_num != idx + 1:
                    self.logger.error(f"[订单冷却期配置] 验证失败: 等级必须从1开始连续，期望等级{idx+1}，实际等级{level_num}")
                    return await self.json_response(msg[10007])
                
                # 4. minutes必须大于0
                if minutes <= 0:
                    self.logger.error(f"[订单冷却期配置] 验证失败: 等级{level_num}的时间必须大于0")
                    return await self.json_response(msg[10007])
            
            # 5. 建议验证：等级越高，时间应该越长（仅警告，不阻止）
            for i in range(1, len(levels)):
                prev_minutes = int(levels[i-1]['minutes'])
                curr_minutes = int(levels[i]['minutes'])
                if curr_minutes < prev_minutes:
                    self.logger.warning(
                        f"[订单冷却期配置] 建议警告: 等级{i+1}的时间({curr_minutes}分钟)"
                        f"小于等级{i}的时间({prev_minutes}分钟)，建议递增配置"
                    )
            
            # ========== 构建配置对象 ==========
            from datetime import datetime
            config = {
                "levels": levels,
                "updated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "updated_by": "admin"  # 可以从session获取实际用户名
            }
            
            # 存储到Redis
            config_json = json.dumps(config, ensure_ascii=False)
            await self.application.redis.set("easypaisa_order_cooldown_config", config_json)
            
            # 记录操作日志
            self.logger.info(
                f"[订单冷却期配置] 配置更新成功: 共{len(levels)}个等级, "
                f"范围: {levels[0]['minutes']}分钟 -> {levels[-1]['minutes']}分钟"
            )
            
            result = dict(
                code=20000,
                msg="配置保存成功",
                data={
                    "levels": levels,
                    "total_levels": len(levels),
                    "max_level_minutes": levels[-1]['minutes'],
                    "updated_at": config['updated_at']
                }
            )
            return await self.json_response(result)
            
        except json.JSONDecodeError as e:
            self.logger.error(f"[订单冷却期配置] JSON解析失败: {str(e)}")
            self.logger.error(f"[订单冷却期配置] 请求体内容: {self.request.body}")
            return await self.json_response(msg[10007])
        except Exception as e:
            self.logger.error(f"[订单冷却期配置] 设置订单冷却期配置失败: {str(e)}")
            self.logger.error(traceback.format_exc())
            return await self.json_response(msg[10007])
    
    async def get(self):
        """获取订单冷却期配置"""
        try:
            self.logger.info(f"[订单冷却期配置] 开始获取订单冷却期配置")
            
            # 从Redis读取配置
            config_str = await self.application.redis.get("easypaisa_order_cooldown_config")
            self.logger.info(f"[订单冷却期配置] 从Redis读取到的值: {config_str}")
            
            if config_str:
                # 使用配置的值
                config = json.loads(config_str)
                levels = config.get('levels', [])
                updated_at = config.get('updated_at', '')
                
                self.logger.info(f"[订单冷却期配置] 使用Redis配置: {len(levels)}个等级")
            else:
                # 使用默认配置
                levels = [
                    {"level": 1, "minutes": 30},
                    {"level": 2, "minutes": 120},
                    {"level": 3, "minutes": 360},
                    {"level": 4, "minutes": 1440}
                ]
                updated_at = None
                
                self.logger.info(f"[订单冷却期配置] 使用默认配置: {len(levels)}个等级")
            
            result = dict(
                code=20000,
                msg="获取配置成功",
                data={
                    "levels": levels,
                    "total_levels": len(levels),
                    "max_level_minutes": levels[-1]['minutes'] if levels else 0,
                    "updated_at": updated_at,
                    "is_default": config_str is None
                }
            )
            return await self.json_response(result)
            
        except Exception as e:
            self.logger.error(f"[订单冷却期配置] 获取订单冷却期配置失败: {str(e)}")
            self.logger.error(traceback.format_exc())
            return await self.json_response(msg[10007])


# API路由映射
auto_payout_stats = AutoPayoutStatsHandler
auto_payout_orders = AutoPayoutOrdersHandler
auto_payout_toggle = AutoPayoutToggleHandler
# auto_payout_emergency_stop = AutoPayoutEmergencyStopHandler  # 已禁用：前端按钮已隐藏
auto_payout_monitor = AutoPayoutMonitorHandler
auto_payout_order_detail = AutoPayoutOrderDetailHandler
auto_payout_payment_id_cooldown = AutoPayoutPaymentIdCooldownHandler
auto_payout_order_cooldown_config = AutoPayoutOrderCooldownConfigHandler
