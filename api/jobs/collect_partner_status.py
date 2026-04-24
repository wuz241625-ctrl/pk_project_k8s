import json

import pymysql
import redis
import logging

import sys
import os
from datetime import datetime

# 将项目的主目录添加进系统path，才能直接调用application文件夹下面的模块等
parent_directory = os.path.dirname(__file__)
grandparent_directory = os.path.dirname(parent_directory)
sys.path.append(grandparent_directory)

from config import get_config

LOG_FILE = "collect_partner_status.log"
logger = logging.getLogger()
logger.setLevel(logging.INFO)

import logging
from logging.handlers import TimedRotatingFileHandler
import io

# 使用 io.open 设置编码为 UTF-8
fh = TimedRotatingFileHandler(LOG_FILE, when='MIDNIGHT', interval=1, backupCount=15)
fh.stream = io.open(LOG_FILE, 'a', encoding='utf-8')  # 设置编码为 UTF-8

datefmt = '%Y-%m-%d %H:%M:%S'
format_str = '%(asctime)s %(levelname)s %(message)s '
formatter = logging.Formatter(format_str, datefmt)
fh.setFormatter(formatter)
logger.addHandler(fh)

conf = get_config()

# 主支付处理函数
def collect_partner(rds, connection):
    try:
        logger.info("开始收集合作伙伴的状态信息...")

        with connection.cursor() as cursor:
            #查询分类条件，无条件不执行
            filters_data_sql = """select `value` from sys_settings where name = 'partner_balance_statistics' limit 1"""
            cursor.execute(filters_data_sql)
            filters_data = cursor.fetchone()
            if not filters_data:
                logger.info(f"没有查询到分类的条件信息，执行完毕")
                return
            filters_data = json.loads(filters_data['value'])
            bound_str = filters_data['bound']
            num = int(filters_data['num'])

            #查询通道信息，查询所有通道在线payment
            select_channel_code = """select code from channel"""
            cursor.execute(select_channel_code)
            channel_code = cursor.fetchall()
            logger.info(f"查询到的通道编号 ：{channel_code}")
            #整合各通道的在线payment
            efficient_payment_id_list = []
            for channel_code_data in channel_code:
                list_name = 'payment_active_{channel_code}'.format(channel_code=channel_code_data['code'])
                payment_id_list = rds.lrange(list_name, 0, -1)
                logger.info(f"查询到的通道编号 ：{channel_code_data['code']}下的在线payment数量：{len(payment_id_list)}")
                if payment_id_list:
                    efficient_payment_id_list += payment_id_list
            # payment_online_ds = rds.smembers('payment_online_ds')
            # efficient_payment_id_set = set(efficient_payment_id_list)
            # efficient_payment_id_list = list(payment_online_ds|efficient_payment_id_set)
            efficient_payment_id_list = list(set(efficient_payment_id_list))
            redis_send_orders_ds_false_limit = rds.get('send_orders_ds_false_limit')
            #剔除假码
            if redis_send_orders_ds_false_limit:
                # 如果 Redis 中有值，则将其解码为字符串，并分割成列表
                low_success_payment_ids = redis_send_orders_ds_false_limit.decode('utf-8').split(',')
                logger.info(f"从 Redis 获取到假码列表: {low_success_payment_ids}")
                # 从支付码列表中移除假码
                efficient_payment_id_list = [pid for pid in efficient_payment_id_list if pid.decode('utf-8') not in low_success_payment_ids]
                logger.info(f"假码剔除后剩余有效支付码: {efficient_payment_id_list}")
            if not efficient_payment_id_list:
                logger.info(f"没有查询到在线的payment，执行完毕")
                return

            batch_size = 500
            partner_list = []
            for i in range(0, len(efficient_payment_id_list), batch_size):
                batch_pids = efficient_payment_id_list[i: i + batch_size]
                placeholders = ', '.join(['%s'] * len(batch_pids))
                sql = """select p.id,p.balance from partner p left join payment pay on pay.partner_id=p.id
                                         where pay.certified=1 and pay.status=1 and pay.manual_status=0
                                           and p.certified=1 and p.status=1 and p.type=1 and pay.id in ({sql_payment_id_list})
                                         GROUP BY p.id""".format(sql_payment_id_list=placeholders)
                params = tuple(batch_pid.decode('utf-8') for batch_pid in batch_pids)
                cursor.execute(sql, params)
                partner_list += cursor.fetchall()

            if partner_list:
                partner_list = {partner['id']: partner for partner in partner_list}.values()
                logger.info(f"查询到有效合作伙伴数量：{len(partner_list)}")
                #查询分类条件
                partner_classify = {}
                # partner_classify_id = {}
                filters_data_list = sorted([ int(bound.strip()) for bound in str(bound_str).split(',') if bound])
                for i in range(len(filters_data_list)):
                    bound_min = filters_data_list[i]
                    bound_max = None
                    if i+1 < len(filters_data_list):
                        bound_max = filters_data_list[i+1]
                    partner_classify[str(i)] = 0
                    # partner_classify_id[str(i)] = []
                    for partner_data in partner_list:
                        if bound_max:
                            if partner_data['balance'] >= bound_min and partner_data['balance'] < bound_max:
                                partner_classify[str(i)] = partner_classify[str(i)]+1
                                # partner_classify_id[str(i)].append(partner_data['id'])
                        else:
                            if partner_data['balance'] >= bound_min:
                                partner_classify[str(i)] = partner_classify[str(i)] + 1
                                # partner_classify_id[str(i)].append(partner_data['id'])
                formatted_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                # redis_data = {'time':formatted_now,'data':partner_classify,'ids':partner_classify_id,'bound':bound_str}
                redis_data = {'time': formatted_now, 'data': partner_classify,'bound': bound_str}
                logger.info(f"预存数据：{redis_data}")
                collect_partner_list = rds.lrange("collect_partner_balance_lv", 0, -1)
                while collect_partner_list and len(collect_partner_list) >= num:
                    rds.lpop("collect_partner_balance_lv")
                    collect_partner_list = rds.lrange("collect_partner_balance_lv", 0, -1)
                rds.rpush("collect_partner_balance_lv", json.dumps(redis_data))
                logger.info("收集合作伙伴的状态信息执行完毕！！！")
    except Exception as e:
        logger.exception(f"收集合作伙伴的状态信息过程中发生错误: {e}")
        connection.rollback()

def main():
    try:
        # 使用 with 语句管理 MySQL 和 Redis 连接，确保连接自动关闭
        logger.info("初始化 Redis 和 MySQL 连接...")

        with pymysql.connect(host=conf['mysql_host'],
                             user=conf['mysql_user'],
                             password=conf['mysql_password'],
                             db=conf['mysql_database'],
                             charset='utf8mb4',
                             cursorclass=pymysql.cursors.DictCursor) as connection:

            with redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8') as rds:
                collect_partner(rds, connection)

    except pymysql.MySQLError as e:
        logger.exception(f"MySQL 连接错误: {e}")
    except redis.RedisError as e:
        logger.exception(f"Redis 连接错误: {e}")
    except Exception as e:
        logger.exception(f"主函数运行出错: {e}")

if __name__ == '__main__':
    main()
