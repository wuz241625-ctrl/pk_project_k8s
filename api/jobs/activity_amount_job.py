import logging
import os
import random
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from logging.handlers import TimedRotatingFileHandler

import pymysql

# 将项目主目录添加到系统路径
parent_directory = os.path.dirname(__file__)
grandparent_directory = os.path.dirname(parent_directory)
sys.path.append(grandparent_directory)
from config import get_config

"""
每日4点根据订单统计数据发放奖励
0 4 * * * python activity_amount_job.py
"""

# 配置日志
LOG_FILE = "activity_amount_job.log"
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

# 余额变动
def change_balance(conn, cur, table, user_id, amount, code, record_type, remark=None, merchant_code=None):
    sql_update = 'update {table} set balance=balance + %s where id = %s'.format(table=table)
    sql_select = """select balance{other} from {table} where id = %s""".format(table=table,
                                                                               other=',vip' if table == 'partner' else '')
    sql_insert = """insert into balance_record (code,user_type,user_id,change_before,amount,change_after,record_type,remark,merchant_code) value (%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
    sql_select_vip = """select vip,conditions from vip"""
    sql_update_vip = """update partner set vip=%s where id = %s"""
    try:
        if not cur.execute(sql_select, user_id):
            conn.rollback()
            return False
        _before = (cur.fetchall())[0]['balance']

        if not cur.execute(sql_update, (amount, user_id)):
            conn.rollback()
            return False
        update_sql = cur.mogrify(sql_update, (amount, user_id))
        logger.info('更改金额{sql}'.format(sql=update_sql))
        if not cur.execute(sql_select, user_id):
            conn.rollback()
            logger.warning(cur._last_executed)
            return False
        user = (cur.fetchall())[0]
        partnerBalance = 0

        _after = user['balance']
        if Decimal(_after) < partnerBalance:
            conn.rollback()
            return False
        user_type = 0 if table == 'partner' else 1

        if not cur.execute(sql_insert, (code, user_type, user_id, _before, amount, _after, record_type, remark, merchant_code)):
            conn.rollback()
            return False
        add_balance_record_sql = cur.mogrify(sql_insert, (code, user_type, user_id, _before, amount, _after, record_type, remark, merchant_code))
        logger.info('新增流水{sql}'.format(sql=add_balance_record_sql))
        # vip
        if table == 'partner' and amount > Decimal(0):
            _vip = 0
            # _deposit = 0
            if not cur.execute(sql_select_vip):
                conn.rollback()
                return False
            vips = cur.fetchall()
            for i in vips:
                if _after >= i['conditions']:
                    _vip = i['vip']

            if int(_vip) > user['vip']:
                if int(_vip) > user['vip']:  # 余额够升级时
                    if not cur.execute(sql_update_vip, (_vip, user_id)):
                        conn.rollback()
                        logger.warning('{user_id}改变VIP失败'.format(user_id=user_id))
                        return False
        return True
    except Exception as e:
        logger.exception(e)
        conn.rollback()
        return False

"""
代付订单统计处理逻辑
"""
def process_activity_job(connection):
    start_time = datetime.now()
    logging.info(f"开始执行订单金额满赠奖励发放: {start_time}")
    try:
        # 创建游标
        with connection.cursor() as cursor:
            # 查询金额满赠活动配置
            activities = select_activity(cursor, 1)
            # 遍历活动
            for activity in activities:
                # 查询昨日符合活动的码商
                df_statistics = select_partners_from_df_statistics(cursor, activity.get('participant'),
                                                                   activity.get('prize_limit_min'),
                                                                   activity.get('prize_limit_max'))
                # 遍历每个码商进行奖励
                for df_statistic in df_statistics:
                    try:
                        partner_id = df_statistic['partner_id']
                        partner = select_partners_by_id(cursor, partner_id)
                        if not partner:
                            logging.warning('未找到码商信息,partner_id:{}'.format(partner_id))
                            continue
                        # 内部码商不进行奖励
                        if partner['type'] == 0:
                            logging.warning('内部码商不进行奖励,partner_id:{}'.format(partner_id))
                            continue
                        code = create_code('HD')
                        # 修改码商余额
                        flag = change_balance(connection, cursor, 'partner', partner_id, activity.get('money'), code, 10)
                        if not flag:
                            logging.warning('更改码商余额失败,partner_id:{}'.format(partner_id))
                            continue
                        # 保存日志
                        log_data = {
                            "user_id" : partner_id,
                            "user_name": partner['name'],
                            "prize_id": activity['prize_id'],
                            "prize_title": activity['prize_title'],
                            "prize_detail_id": activity['id'],
                            "money": activity['money']
                        }
                        save_prize_earn_log(cursor, log_data)
                        logging.info(
                            '码商partner_id:{partner_id}在{stats_date}订单成功金额{order_amount_success},达到活动“{activity_name}”奖励规则范围{prize_limit_min}-{prize_limit_max}，奖励金额{money}'.format(
                                partner_id=partner_id, stats_date=df_statistic['stats_date'],
                                order_amount_success=df_statistic['order_amount_success'],
                                prize_limit_min=activity['prize_limit_min'],
                                prize_limit_max=activity['prize_limit_max'],
                                activity_name=activity['title'], money=activity.get('money')))
                    except Exception as e:
                        logging.error(f'处理partner={partner_id}的process_activity_job()发生错误：{e}')
        end_time = datetime.now()
        duration = end_time - start_time
        logging.info(f"订单金额满赠奖励发放任务结束，耗时: {duration}")
    except Exception as e:
        logging.error(f'订单金额满赠活动任务执行过程发生错误: {e}')
        connection.rollback()
        raise e
    else:
        connection.commit()

"""
订单数量满赠
"""
def process_activity_num_job(connection):
    start_time = datetime.now()
    logging.info(f"开始执行订单数量满赠奖励发放: {start_time}")
    try:
        # 创建游标
        with connection.cursor() as cursor:
            # 查询订单数量满赠活动配置
            activities = select_activity(cursor, 2)
            # 遍历活动
            for activity in activities:
                # 查询昨日符合活动的码商
                df_statistics = select_partners_from_df_statistics_by_order_num(cursor, activity.get('participant'),
                                                                   activity.get('prize_limit_min'),
                                                                   activity.get('prize_limit_max'))
                # 遍历每个码商进行奖励
                for df_statistic in df_statistics:
                    try:
                        partner_id = df_statistic['partner_id']
                        partner = select_partners_by_id(cursor, partner_id)
                        if not partner:
                            logging.warning('未找到码商信息,partner_id:{}'.format(partner_id))
                            continue
                        # 内部码商不进行奖励
                        if partner['type'] == 0:
                            logging.warning('内部码商不进行奖励,partner_id:{}'.format(partner_id))
                            continue
                        code = create_code('HD')
                        # 修改码商余额
                        flag = change_balance(connection, cursor, 'partner', partner_id, activity.get('money'), code, 10)
                        if not flag:
                            logging.warning('更改码商余额失败,partner_id:{}'.format(partner_id))
                            continue
                        # 保存日志
                        log_data = {
                            "user_id" : partner_id,
                            "user_name": partner['name'],
                            "prize_id": activity['prize_id'],
                            "prize_title": activity['prize_title'],
                            "prize_detail_id": activity['id'],
                            "money": activity['money']
                        }
                        save_prize_earn_log(cursor, log_data)
                        logging.info(
                            '码商partner_id:{partner_id}在{stats_date}订单成功数量{order_success},达到活动“{activity_name}”奖励规则范围{prize_limit_min}-{prize_limit_max}，奖励金额{money}'.format(
                                partner_id=partner_id, stats_date=df_statistic['stats_date'],
                                order_success=df_statistic['order_success'],
                                prize_limit_min=activity['prize_limit_min'],
                                prize_limit_max=activity['prize_limit_max'],
                                activity_name=activity['title'], money=activity.get('money')))
                    except Exception as e:
                        logging.error(f'处理partner={partner_id}的process_activity_num_job()发生错误：{e}')
        end_time = datetime.now()
        duration = end_time - start_time
        logging.info(f"订单数量满赠奖励发放任务结束，耗时: {duration}")
    except Exception as e:
        logging.error(f'订单数量满赠活动任务执行过程发生错误: {e}')
        connection.rollback()
        raise e
    else:
        connection.commit()

"""
保存中奖记录
"""
def save_prize_earn_log(dbCursor, log_data):
    insert_query = """
        INSERT INTO prize_earn_log (
            user_id,
            user_name,
            prize_id,
            prize_title,
            prize_detail_id,
            money,
            created_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, NOW()
        )
    """

    dbCursor.execute(insert_query, (
        log_data['user_id'],
        log_data['user_name'],
        log_data['prize_id'],
        log_data['prize_title'],
        log_data['prize_detail_id'],
        log_data['money']
    ))

"""
查询码商日统计，查询符合活动规则的码商
"""
def select_partners_from_df_statistics(dbCursor, ids, prize_limit_min, prize_limit_max):
    # 获取当前时间
    current_time = datetime.now()

    # 计算昨日时间
    yesterday = current_time - timedelta(days=1)
    yesterday_str = yesterday.strftime('%Y-%m-%d')
    if ids == '-1':
        query = """
                select * from statistics_daily_partner_orders_df 
                where order_amount_success >= %s and order_amount_success < %s and stats_date = %s
            """
        dbCursor.execute(query, (prize_limit_min, prize_limit_max, yesterday_str))
    else :
        query = """
                select * from statistics_daily_partner_orders_df 
                where order_amount_success >= %s and order_amount_success < %s and stats_date = %s and partner_id in (%s)
            """
        dbCursor.execute(query, (prize_limit_min, prize_limit_max, yesterday_str, ids))
    return dbCursor.fetchall()


"""
查询码商日统计，查询符合活动规则的订单数量的码商
"""
def select_partners_from_df_statistics_by_order_num(dbCursor, ids, prize_limit_min, prize_limit_max):
    # 获取当前时间
    current_time = datetime.now()

    # 计算昨日时间
    yesterday = current_time - timedelta(days=1)
    yesterday_str = yesterday.strftime('%Y-%m-%d')
    if ids == '-1':
        query = """
                select * from statistics_daily_partner_orders_df 
                where order_success >= %s and order_success < %s and stats_date = %s
            """
        dbCursor.execute(query, (prize_limit_min, prize_limit_max, yesterday_str))
    else :
        query = """
                select * from statistics_daily_partner_orders_df 
                where order_success >= %s and order_success < %s and stats_date = %s and partner_id in (%s)
            """
        dbCursor.execute(query, (prize_limit_min, prize_limit_max, yesterday_str, ids))
    return dbCursor.fetchall()
"""
根据id查询码商
"""
def select_partners_by_id(dbCursor, id):
    """获取订单统计数据"""
    query = """
        SELECT * FROM partner where id=%s
    """
    dbCursor.execute(query, (id))
    return dbCursor.fetchone()


"""
获取活动配置
"""
def select_activity(dbCursor, type):
    time = datetime.now()
    """获取活动配置"""
    query = """
        SELECT detail.*,p.participant FROM prize_setting_detail detail
        left join  prize_setting p  on p.id  = detail.prize_id
        where p.status=1 and detail.status =1 and p.begin_at <= %s and p.end_at > %s and p.type = %s 
    """
    dbCursor.execute(query, (time,time,type))
    return dbCursor.fetchall()

"""
创建编码
"""
def create_code(PRE='R'):
    return PRE + ''.join(str(datetime.now().timestamp()).split('.')) + str(random.randint(1000, 9999))


def main():
    """主函数"""
    start_time = datetime.now()
    logging.info(f"开始执行每日活动奖励发放: {start_time}")

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
        process_activity_job(connection)
        # 执行订单数量满赠活动任务
        process_activity_num_job(connection)

    except Exception as e:
        logging.error(f'任务执行失败: {e}')
    finally:
        if connection:
            connection.close()
        end_time = datetime.now()
        duration = end_time - start_time
        logging.info(f"活动奖励发放任务结束，耗时: {duration}")


if __name__ == '__main__':
    logging.info("开始执行每日活动奖励发放")
    main()
