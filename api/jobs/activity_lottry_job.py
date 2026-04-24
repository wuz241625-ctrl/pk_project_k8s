import logging
import os
import random
import sys
import traceback
from datetime import datetime, timedelta
from decimal import Decimal
from logging.handlers import TimedRotatingFileHandler

import pymysql
import redis

# 将项目主目录添加到系统路径
parent_directory = os.path.dirname(__file__)
grandparent_directory = os.path.dirname(parent_directory)
sys.path.append(grandparent_directory)
from config import get_config

"""
每日4点根据订单统计数据 计算码商抽奖机会及奖池
0 4 * * * python activity_lottry_job.py
"""

# 配置日志
LOG_FILE = "activity_lottry_job.log"
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


# 增加码商抽奖机会
def add_lottery_change(conn, cur, activity, df_statistic):
    sql_select = """ select * from prize_lottery_chance where user_id = %s"""

    sql_insert = """insert into prize_lottery_chance (user_id, chance_num, created_at, updated_at) values (%s, %s, now(), now())"""
    sql_update = """update prize_lottery_chance set chance_num=%s,updated_at=now() where id = %s"""

    sql_add_log = """insert into prize_lottery_chance_log (user_id, prize_id, before_num, num, after_num, remark, created_at) values ( %s, %s, %s, %s, %s, %s, now())"""

    activity_id = activity['id']
    user_id = df_statistic['partner_id']
    order_success = df_statistic.get('order_success')
    lottery_chance_setting = activity.get('lottery_chance_setting')
    # 计算码商可获得的
    chance_num = order_success // activity.get('lottery_chance_setting')

    try:
        remark = '码商{user_id}代付订单数量为{order_success},满足抽奖活动{activity_id}设定的抽奖机会设置"满{lottery_chance_setting}单奖励一次抽奖机会"，奖励{chance_num}次抽奖机会'.format(
            user_id=user_id, order_success=order_success, activity_id=activity_id,
            lottery_chance_setting=lottery_chance_setting, chance_num=chance_num)

        # 查询码商是否已有抽奖机会
        if cur.execute(sql_select, user_id):
            _before = (cur.fetchall())[0]
            _before_num = _before['chance_num']
            _after_num = _before_num + chance_num

            # 修改抽奖机会
            if not cur.execute(sql_update, (_after_num, _before['id'])):
                conn.rollback()
                return False

        else:
            # 新增抽奖机会
            _before_num = 0
            _after_num = chance_num

            if not cur.execute(sql_insert, (user_id, _after_num)):
                conn.rollback()
                return False

        # 新增 抽奖机会记录
        if not cur.execute(sql_add_log, (user_id, activity_id, _before_num, chance_num, _after_num, remark)):
            conn.rollback()
            return False
        return True
    except Exception as e:
        logger.exception(e)
        conn.rollback()
        return False


"""
抽奖机会计算任务
"""


def process_activity_lottery_job(connection):
    start_time = datetime.now()
    logging.info(f"开始执行抽奖机会计算任务: {start_time}")
    try:
        # 创建游标
        with connection.cursor() as cursor:
            # 查询金额满赠活动配置
            activity = select_lottery_activity(cursor)
            if not activity:
                logging.info(f"未查询到可执行的抽奖活动配置，抽奖机会计算任务结束")
                return

            # 查询昨日符合活动的码商
            df_statistics = select_partners_from_df_statistics_by_order_num(cursor, activity.get('participant'),
                                                                            activity.get('lottery_chance_setting'))

            # 增加码商的抽奖机会
            for df_statistic in df_statistics:
                add_lottery_change(connection, cursor, activity, df_statistic)

        end_time = datetime.now()
        duration = end_time - start_time
        logging.info(f"抽奖机会计算任务结束，耗时: {duration}")
    except Exception as e:
        tb_str = traceback.format_exc()
        error_message = ''.join(tb_str)
        logging.error('抽奖机会计算任务执行过程发生错误: {}\n {}', e, error_message)
        connection.rollback()
        raise e
    else:
        connection.commit()


"""
处理资金池资金积累
"""


def process_pool_amount_job(connection):
    rds = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
    start_time = datetime.now()
    logging.info(f"开始执行资金池资金增加: {start_time}")
    try:
        # 创建游标
        with connection.cursor() as cursor:

            # 获取当前时间
            current_time = datetime.now()
            busy_key = 'prize_pool_lock'

            # 计算昨日时间
            yesterday = current_time - timedelta(days=1)
            yesterday_str = yesterday.strftime('%Y-%m-%d')
            # 查询所有码商昨日成交单子数量
            sql_select = """select sum(order_success) total from statistics_daily_partner_orders_df  where stats_date = %s """
            cursor.execute(sql_select, yesterday_str)
            order_success_num = cursor.fetchone()['total']
            if order_success_num is None:
                return False

            # 获取锁，10秒内锁定
            if not rds.setnx(busy_key, 1):
                return False
            rds.expire(busy_key, 10)

            # 增加资金池的资金
            sql_query = """ select * from prize_pool where id = 1 """
            sql_update = """ update prize_pool set pool_amount = %s, updated_at = now() where id = 1"""
            sql_add_log = """ insert into prize_pool_log (code, record_type, change_before, amount, change_after, remark, created_at)
             values (%s, %s, %s, %s, %s, %s, now()); """

            # 查询资金池资金
            if not cursor.execute(sql_query, ()):
                connection.rollback()
                return False

            amount = order_success_num * 5

            _before = (cursor.fetchall())[0]
            _before_amount = _before['pool_amount']
            _after_amount = _before_amount + amount

            # 修改奖池
            if not cursor.execute(sql_update, _after_amount):
                connection.rollback()
                return False

            # 记录奖池变动记录
            code = create_code('JC')
            remark = "{yesterday_str}码商代付订单数量为{order_success_num}，奖池金额增加{amount}".format(
                yesterday_str=yesterday_str, order_success_num=order_success_num, amount=amount)

            if not cursor.execute(sql_add_log, (code, 1, _before_amount, amount, _after_amount, remark)):
                connection.rollback()
                return False

        end_time = datetime.now()
        duration = end_time - start_time
        logging.info(f"资金池资金增加任务结束，耗时: {duration}")
    except Exception as e:
        tb_str = traceback.format_exc()
        error_message = ''.join(tb_str)
        logging.error('资金池资金增加任务执行过程发生错误: {}\n {}', e, error_message)
        connection.rollback()
        raise e
    else:
        connection.commit()
    finally:
        # 执行完成删除锁
        rds.delete(busy_key)


# 查询码商日统计，查询符合活动规则的订单数量的码商
def select_partners_from_df_statistics_by_order_num(dbCursor, ids, lottery_chance_setting):
    # 获取当前时间
    current_time = datetime.now()

    # 计算昨日时间
    yesterday = current_time - timedelta(days=1)
    yesterday_str = yesterday.strftime('%Y-%m-%d')
    if ids == '-1':
        query = """
                select * from statistics_daily_partner_orders_df 
                where order_success >= %s and stats_date = %s
            """
        dbCursor.execute(query, (lottery_chance_setting, yesterday_str))
    else:
        query = """
                select * from statistics_daily_partner_orders_df 
                where order_success >= %s and stats_date = %s and partner_id in (%s)
            """
        dbCursor.execute(query, (lottery_chance_setting, yesterday_str, ids))
    return dbCursor.fetchall()


# 查询昨日码商成功交易的订单总数
def select_partners_success_order_num(dbCursor):
    # 获取当前时间
    current_time = datetime.now()

    # 计算昨日时间
    yesterday = current_time - timedelta(days=1)
    yesterday_str = yesterday.strftime('%Y-%m-%d')
    query = """
            select sum(order_success) from statistics_daily_partner_orders_df 
            where  stats_date = %s
        """
    dbCursor.execute(query, yesterday_str)
    return dbCursor.fetchone()


# 根据id查询码商
def select_partners_by_id(dbCursor, id):
    """获取订单统计数据"""
    query = """
        SELECT * FROM partner where id=%s
    """
    dbCursor.execute(query, (id))
    return dbCursor.fetchone()


# 查询抽奖活动配置
def select_lottery_activity(dbCursor):
    time = datetime.now()
    """获取活动配置"""
    query = """
        SELECT * FROM prize_setting p
        where p.status=1 and p.begin_at <= %s and p.end_at > %s and p.type = 0 limit 1
    """
    dbCursor.execute(query, (time, time))
    return dbCursor.fetchone()


# 创建编码
def create_code(PRE='R'):
    return PRE + ''.join(str(datetime.now().timestamp()).split('.')) + str(random.randint(1000, 9999))


def main():
    """主函数"""
    start_time = datetime.now()
    logging.info(f"开始执行抽奖活动定时任务: {start_time}")

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
        # 执行订单金额满赠活动任务
        process_activity_lottery_job(connection)
        # 处理资金池任务
        process_pool_amount_job(connection)

    except Exception as e:
        tb_str = traceback.format_exc()
        error_message = ''.join(tb_str)
        logging.error('任务执行失败: {}\n {}', e, error_message)
    finally:
        if connection:
            connection.close()
        end_time = datetime.now()
        duration = end_time - start_time
        logging.info(f"抽奖活动定时任务任务结束，耗时: {duration}")


if __name__ == '__main__':
    main()
