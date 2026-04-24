import pymysql
import redis
import logging
from logging.handlers import TimedRotatingFileHandler

import sys
import os

# 将项目的主目录添加进系统path，才能直接调用application文件夹下面的模块等
parent_directory = os.path.dirname(__file__)
grandparent_directory = os.path.dirname(parent_directory)
sys.path.append(grandparent_directory)

from config import get_config

LOG_FILE = "clear_redis_dsdf.log"
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

# 支付处理的具体逻辑
def process_payment(payment_id, bank_type_id, rds, connection):
    logger.info(f"处理支付记录 {payment_id}，银行类型 {bank_type_id}...")
    
    try:
        # 查询 `bank_type` 表中的 `name`
        with connection.cursor() as cursor:
            cursor.execute("SELECT name FROM bank_type WHERE id=%s", (bank_type_id,))
            bank_type_record = cursor.fetchone()

        if not bank_type_record:
            logger.error(f"未找到银行类型 ID 为 {bank_type_id} 的记录")
            return
        
        # bank_name = bank_type_record['name']
        # logger.info(f"银行类型名称: {bank_name}")

        # 初始化 bank 列表
        # banks = ['freecharge']
        login_on = dict({
        14:'phonepe',
        16:'freecharge',
        17:'mobi',
        21:'airtel',
        30:'amazon',
        80:'jio',
        90:'maha'
        })

        # 检查并清理 Redis 中的状态
        ds_exists = rds.sismember('payment_online_ds', payment_id)
        logger.info(f"支付ID: {payment_id} 在 'payment_online_ds' 中的状态为: {ds_exists}")
        # 不判断代付  df_exists 20241014
        df_exists = rds.sismember('payment_online_df', payment_id)

        # 检查 `login_on_{bank}_{id}` 是否为空或不存在
        login_key = 'login_on_{bank}_{id}'.format(bank=login_on[int(bank_type_id)], id=payment_id)
        logger.info(f"构造的 Redis 键值为: {login_key}")

        login_key_value = rds.get(login_key)
        logger.info(f"获取 Redis 键 {login_key} 的值为: {login_key_value}")

        # or not df_exists 不判断代付  df_exists  payment_id  14，21，30 ( or (int(bank_type_id) not in [14, 21, 30] and not df_exists) )  20241014
        if not ds_exists or (int(bank_type_id) not in [14, 21, 30] and not df_exists) or not login_key_value:
            logger.info(f"支付ID: {payment_id} 需要进行状态清理")
            logger.info(f"清除 Redis 中的支付 ID {payment_id}")

            # 设置 Redis 键
            if int(bank_type_id) in login_on.keys():
                redis_key = 'login_off_realtime_{bank}_{id}'.format(bank=login_on[int(bank_type_id)], id=payment_id)
                # redis_key = f'login_off_realtime_{bank_name}_{payment_id}'
                rds.set(redis_key, '1', ex=2 * 60)  # 设置过期时间为 2 分钟
                logger.info(f"成功设置 Redis 键 {redis_key}")

            rds.srem('payment_online_ds', payment_id)
            rds.srem('payment_online_df', payment_id)
            rds.lrem('payment_active_df', 0, payment_id)

            # login_key = f"login_on_{bank_name}_{payment_id}"
            login_key = 'login_on_{bank}_{id}'.format(bank=login_on[int(bank_type_id)], id=payment_id)
            rds.delete(login_key)
            logger.info(f"删除 Redis 键 {login_key}")

            # 更新数据库中的 `status` 为 0
            logger.info(f"更新支付记录 {payment_id} 的状态为 0")
            with connection.cursor() as cursor:
                cursor.execute("UPDATE payment SET status=0 WHERE id=%s", (payment_id,))
                connection.commit()
        else:
            logger.info(f"支付ID: {payment_id} 不需要状态清理")

    except Exception as e:
        logger.exception(f"处理支付记录 {payment_id} 时发生错误: {e}")
        connection.rollback()

# 主支付处理函数
def process_payments(rds, connection):
    try:
        logger.info("开始处理支付记录...")
        with connection.cursor() as cursor:
            logger.info("开始查询需要处理的支付记录")
            cursor.execute("SELECT id, bank_type FROM payment WHERE bank_type in (16, 14, 17, 21, 30) AND status=1 AND certified=1 ")
            payments = cursor.fetchall()
            logger.info(f"查询到 {len(payments)} 条记录需要处理: {payments}")

        for payment in payments:
            payment_id = payment['id']
            bank_type = payment['bank_type']
            
            # 打印单条支付记录的详情
            logger.info(f"开始处理支付记录 ID: {payment_id}, Bank Type: {bank_type}")
            process_payment(payment_id, bank_type, rds, connection)
            logger.info(f"支付记录 ID: {payment_id} 处理成功")

        logger.info("支付记录处理完成")
    except Exception as e:
        logger.exception(f"处理支付记录过程中发生错误: {e}")
        connection.rollback()

# async def setup_redis_data(redis_client):
#     logger = logging.getLogger('payment_processor')

#     payment_id = 510133
#     bank_name = "FREECHARGE"
    
#     logger.info("Setting up Redis test data...")

#     # 插入键值对 login_on_FREECHARGE_510133
#     await redis_client.set(f"login_on_{bank_name}_{payment_id}", "some_login_data")

#     # 将 payment_id 插入到 payment_online_ds 集合中
#     await redis_client.sadd("payment_online_ds", payment_id)

#     # 将 payment_id 插入到 payment_online_df 集合中
#     await redis_client.sadd("payment_online_df", payment_id)

#     logger.info(f"Redis data setup complete for payment {payment_id}")

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
                process_payments(rds, connection)

    except pymysql.MySQLError as e:
        logger.exception(f"MySQL 连接错误: {e}")
    except redis.RedisError as e:
        logger.exception(f"Redis 连接错误: {e}")
    except Exception as e:
        logger.exception(f"主函数运行出错: {e}")

if __name__ == '__main__':
    main()
