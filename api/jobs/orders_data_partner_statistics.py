import logging
import os
import sys
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler

import pymysql

# 将项目主目录添加到系统路径
parent_directory = os.path.dirname(__file__)
grandparent_directory = os.path.dirname(parent_directory)
sys.path.append(grandparent_directory)
from config import get_config

"""
每日3点统计前一天的订单数据并保存到数据库
0 3 * * * python orders_data_partner_statistics.py
"""

# 配置日志
LOG_FILE = "orders_data_partner_statistics.log"
datefmt = '%Y-%m-%d %H:%M:%S'
format_str = '%(asctime)s %(levelname)s %(message)s '
logger = logging.getLogger()
logger.setLevel(logging.INFO)
handler = TimedRotatingFileHandler(LOG_FILE, when='MIDNIGHT', interval=1, backupCount=15, encoding='utf-8')
formatter = logging.Formatter(format_str, datefmt)
handler.setFormatter(formatter)
logger.addHandler(handler)

# 读取配置
conf = get_config()


def get_yesterday_date_range():
    """获取昨天的日期范围"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    return yesterday, today - timedelta(seconds=1)

"""
查询获得指定码商的订单数据
"""
def get_orders_ds_statistics(dbCursor, partner_id, start_time, end_time):
    """获取订单统计数据"""
    query = """
        select 
            t1.*, 
            if(t1.order_success = 0 and t1.order_fail = 0, 0, t1.order_success/ (t1.order_success + t1.order_fail)) as rate 
        from (
            SELECT 
                %s as partner_id,
                COUNT(*) as order_total,
                COALESCE(SUM(CASE WHEN status > 2 THEN 1 ELSE 0 END), 0) as order_success,
                COALESCE(SUM(CASE WHEN status < 0 THEN 1 ELSE 0 END), 0) as order_fail,
                COALESCE(SUM(amount), 0) as order_amount,
                COALESCE(SUM(CASE WHEN status > 2 THEN amount ELSE 0 END), 0) as order_amount_success,
                COALESCE(SUM(CASE WHEN status < 0 THEN amount ELSE 0 END), 0) as order_amount_fail,
                COALESCE(SUM(CASE WHEN status > 2 THEN COALESCE(poundage, 0) ELSE 0 END), 0) as order_poundage
            FROM orders_ds 
            WHERE partner_id = %s and time_success BETWEEN %s AND %s
        ) t1
    """
    dbCursor.execute(query, (partner_id, partner_id, start_time, end_time))
    return dbCursor.fetchone()


"""
获得代付订单统计数据
"""
def get_orders_df_statistics(dbCursor, partner_id, start_time, end_time):
    """获取订单统计数据"""
    query = """
        select 
            t1.*, 
            if(t1.order_success = 0 and t1.order_fail = 0, 0, t1.order_success/ (t1.order_success + t1.order_fail)) as rate 
        from (
            SELECT 
                %s as partner_id,
                COUNT(*) as order_total,
                COALESCE(SUM(CASE WHEN status > 2 THEN 1 ELSE 0 END), 0) as order_success,
                COALESCE(SUM(CASE WHEN status < 0 THEN 1 ELSE 0 END), 0) as order_fail,
                COALESCE(SUM(amount), 0) as order_amount,
                COALESCE(SUM(CASE WHEN status > 2 THEN amount ELSE 0 END), 0) as order_amount_success,
                COALESCE(SUM(CASE WHEN status < 0 THEN amount ELSE 0 END), 0) as order_amount_fail,
                COALESCE(SUM(CASE WHEN status > 2 THEN COALESCE(poundage, 0) ELSE 0 END), 0) as order_poundage
            FROM orders_df 
            WHERE partner_id = %s and time_success BETWEEN %s AND %s
        ) t1
    """
    dbCursor.execute(query, (partner_id, partner_id, start_time, end_time))
    return dbCursor.fetchone()


"""
保存代收订单统计数据到数据库
"""
def save_orders_ds_statistics(dbCursor, partner_id, stats_data, stats_date):
    # 如果订单数为0，不保存统计数据
    if not stats_data['order_total']:
        logging.info(f"日数据统计，码商日代收订单数为0，不保存数据，日期：{stats_date}, 码商ID：{stats_data['partner_id']}")
        return
    # 确保所有值都不为 None
    safe_stats_data = {
        'partner_id': int(stats_data['partner_id'] or 0),
        'order_total': int(stats_data['order_total'] or 0),
        'order_success': int(stats_data['order_success'] or 0),
        'order_fail': int(stats_data['order_fail'] or 0),
        'order_amount': float(stats_data['order_amount'] or 0),
        'order_amount_success': float(stats_data['order_amount_success'] or 0),
        'order_amount_fail': float(stats_data['order_amount_fail'] or 0),
        'rate': float(stats_data['rate'] or 0),
        'order_poundage': float(stats_data['order_poundage'] or 0)
    }
    insert_query = """
        INSERT INTO statistics_daily_partner_orders_ds (
            partner_id,
            stats_date,
            order_total,
            order_success,
            order_fail,
            order_amount,
            order_amount_success,
            order_amount_fail,
            order_poundage,
            rate,
            created_at,
            updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
        )
    """

    dbCursor.execute(insert_query, (
        safe_stats_data['partner_id'],
        stats_date,
        safe_stats_data['order_total'],
        safe_stats_data['order_success'],
        safe_stats_data['order_fail'],
        safe_stats_data['order_amount'],
        safe_stats_data['order_amount_success'],
        safe_stats_data['order_amount_fail'],
        safe_stats_data['order_poundage'],
        safe_stats_data['rate']
    ))


"""
保存代付订单统计数据到数据库
"""
def save_orders_df_statistics(dbCursor, partner_id, stats_data, stats_date):
    # 如果订单数为0，不保存统计数据
    if not stats_data['order_total']:
        logging.info(f"日数据统计，码商日代付订单数为0，不保存数据，日期：{stats_date}, 码商ID：{stats_data['partner_id']}")
        return
    # 确保所有值都不为 None
    safe_stats_data = {
        'partner_id': int(stats_data['partner_id'] or 0),
        'order_total': int(stats_data['order_total'] or 0),
        'order_success': int(stats_data['order_success'] or 0),
        'order_fail': int(stats_data['order_fail'] or 0),
        'order_amount': float(stats_data['order_amount'] or 0),
        'order_amount_success': float(stats_data['order_amount_success'] or 0),
        'order_amount_fail': float(stats_data['order_amount_fail'] or 0),
        'order_poundage': float(stats_data['order_poundage'] or 0),
        'rate': float(stats_data['rate'] or 0)
    }

    insert_query = """
        INSERT INTO statistics_daily_partner_orders_df (
            partner_id,
            stats_date,
            order_total,
            order_success,
            order_fail,
            order_amount,
            order_amount_success,
            order_amount_fail,
            order_poundage,
            rate,
            created_at,
            updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
        )
    """

    dbCursor.execute(insert_query, (
        safe_stats_data['partner_id'],
        stats_date,
        safe_stats_data['order_total'],
        safe_stats_data['order_success'],
        safe_stats_data['order_fail'],
        safe_stats_data['order_amount'],
        safe_stats_data['order_amount_success'],
        safe_stats_data['order_amount_fail'],
        safe_stats_data['order_poundage'],
        safe_stats_data['rate']
    ))


"""
代收订单统计处理逻辑
"""
def process_orders_ds(cursor, partner_id):
    logging.info("开始统计代收订单数据")

    # 获取昨天的日期范围
    start_time, end_time = get_yesterday_date_range()
    stats_date = start_time.date()

    logging.info(f"统计时间范围: {start_time} - {end_time}")

    # 获取统计数据
    stats_data = get_orders_ds_statistics(cursor, partner_id, start_time, end_time)

    if not stats_data:
        logging.warning("未获取到代收订单统计数据")
        return

    logging.info(f"代收订单统计数据: {stats_data}")

    # 保存统计数据
    save_orders_ds_statistics(cursor, partner_id, stats_data, stats_date)

    logging.info("代收订单统计数据已保存")


"""
代付订单统计处理逻辑
"""
def process_orders_df(cursor, partner_id):
    logging.info("开始统计代付订单数据")

    # 获取昨天的日期范围
    start_time, end_time = get_yesterday_date_range()
    stats_date = start_time.date()

    logging.info(f"统计时间范围: {start_time} - {end_time}")

    # 获取统计数据
    stats_data = get_orders_df_statistics(cursor, partner_id, start_time, end_time)

    if not stats_data:
        logging.warning("未获取到代付订单统计数据")
        return

    logging.info(f"代付订单统计数据: {stats_data}")

    # 保存统计数据
    save_orders_df_statistics(cursor, partner_id, stats_data, stats_date)

    logging.info("代付订单统计数据已保存")

"""
代付订单统计处理逻辑
"""
def process_partners(connection):
    logging.info("开始查询码商")

    try:
        # 创建游标
        with connection.cursor() as cursor:
            # 查询码商
            partners = select_partners(cursor)
            # 遍历每个码商进行统计
            for partner in partners:
                partner_id = partner['id']
                try:
                    # 执行代收订单的统计过程
                    process_orders_ds(cursor, partner_id)
                except Exception as e:
                    logging.error(f'处理partner={partner_id}的process_orders_ds()发生错误：{e}')
                try:
                    # 执行代付订单的统计过程
                    process_orders_df(cursor, partner_id)
                except Exception as e:
                    logging.error(f'处理partner={partner_id}的process_orders_df()发生错误：{e}')
    except Exception as e:
        logging.error(f'代付订单统计过程发生错误: {e}')
        connection.rollback()
        raise e
    else:
        connection.commit()


"""
获得所有码商
"""
def select_partners(dbCursor):
    """获取订单统计数据（type = 1 外部， status = 1 启用）"""
    query = """
        SELECT id FROM partner where type = 1
    """
    dbCursor.execute(query, ())
    return dbCursor.fetchall()


def main():
    """主函数"""
    start_time = datetime.now()
    logging.info(f"开始执行订单统计任务: {start_time}")

    connection = None

    try:
        # 连接数据库
        connection = pymysql.connect(
            host=conf['mysql_host'],
            user=conf['mysql_user'],
            password=conf['mysql_password'],
            db=conf['mysql_database'],
            charset='utf8mb4',
            # 配置游标类型，返回结果定义为字典
            cursorclass=pymysql.cursors.DictCursor
        )
        connection.ping()
        # 查询码商并保存统计数据
        process_partners(connection)

    except Exception as e:
        logging.error(f'任务执行失败: {e}')
    finally:
        if connection:
            connection.close()
        end_time = datetime.now()
        duration = end_time - start_time
        logging.info(f"统计任务结束，耗时: {duration}")


if __name__ == '__main__':
    logging.info("开始执行每日订单统计")
    main()