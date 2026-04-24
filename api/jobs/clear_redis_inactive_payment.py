import redis
import pymysql
import logging

from config import get_config
from logging.handlers import TimedRotatingFileHandler

LOG_FILE = "clear_redis_inactive_payment.log"
logger = logging.getLogger()
logger.setLevel(logging.INFO)
fh = TimedRotatingFileHandler(LOG_FILE, when='MIDNIGHT', interval=1, backupCount=15)
datefmt = '%Y-%m-%d %H:%M:%S'
format_str = '%(asctime)s %(levelname)s %(message)s '
formatter = logging.Formatter(format_str, datefmt)
fh.setFormatter(formatter)
logger.addHandler(fh)
conf = get_config()

EASYPAISA_RUNTIME_ONLINE_KEY = "easypaisa_runtime:index:online"


def _decode_text(value):
    if isinstance(value, bytes):
        return value.decode('utf-8')
    return str(value)

def get_all_active_payment_ids_from_redis(rds):
    active_payment_ids = {}

    for payment_id in rds.smembers(EASYPAISA_RUNTIME_ONLINE_KEY):
        pid = _decode_text(payment_id)
        if pid.isdigit():
            active_payment_ids[pid] = 'easypaisa'
            logger.info(f"从 runtime 在线索引读取 EasyPaisa payment_id: {pid}")

    for key_bytes in rds.scan_iter('login_on_*'):
        key_str = _decode_text(key_bytes)
        parts = key_str.split('_')
        # 检查 key 格式是否正确 (login_on_bankname_id)
        # 确保至少有 4 部分：'login', 'on', 'bankname', 'id'
        if len(parts) >= 4 and parts[0] == 'login' and parts[1] == 'on':
            bank_name_or_id = parts[2]
            
            # pid = "_".join(parts[3:])
            if parts[3].isdigit():
                pid = parts[3]
                logger.info(f"原始数据: {parts}, PID is a number: {pid}")

            else:
                pid = None
                logger.warning(f"原始数据: {parts}, PID is not a number, skipping...")

            if pid is not None:
                logger.info(f"原始数据: {parts}, Storing PID: {pid} with Bank Name/ID: {bank_name_or_id}")

                # 直接将 bank_name_or_id 作为 bank_type_id 存入
                active_payment_ids[pid] = bank_name_or_id
            else:
                logger.warning(f"原始数据: {parts}, PID was None.")

        else:
            logger.warning(f"发现格式不符合 'login_on_bankname_id' 模式的 Redis Key: {key_str}")
    logger.info(f"从 Redis 获取到 {len(active_payment_ids)} 个可能的活跃支付码ID。{active_payment_ids}")
    return active_payment_ids

def batch_query_order_counts(connection, payment_ids, time_window_seconds, batch_size=500):
    order_counts = {}
    
    if not payment_ids:
        return order_counts

    pids_list = list(payment_ids)
    
    for i in range(0, len(pids_list), batch_size):
        batch_pids = pids_list[i : i + batch_size]
        placeholders = ', '.join(['%s'] * len(batch_pids))
        
        sql = f"""
            SELECT payment_id, COUNT(*) AS count
            FROM orders_ds
            WHERE payment_id IN ({placeholders}) AND time_create >= NOW() - INTERVAL %s SECOND
            GROUP BY payment_id
        """
        params = tuple(batch_pids) + (time_window_seconds,)
        
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                results = cursor.fetchall()
                for row in results:
                    order_counts[row['payment_id']] = row['count']
            logger.debug(f"数据库批量查询完成，处理了 {len(batch_pids)} 个支付ID。")
        except Exception as e:
            logger.exception(f"数据库批量查询支付ID {batch_pids[:5]}...时发生错误: {e}")
            for pid in batch_pids:
                order_counts.setdefault(pid, 0) 

    return order_counts

def clean_inactive_payments(rds, connection):
    try:
        time_window_seconds = 3 * 24 * 60 * 60 

        logger.info("开始检查三天内没有订单的支付码...")

        active_payment_ids_with_bank = get_all_active_payment_ids_from_redis(rds)
        
        if not active_payment_ids_with_bank:
            logger.info("未从 Redis 获取到任何活跃支付码ID，清理完成。")
            return

        payment_ids_to_check_db = list(active_payment_ids_with_bank.keys())
        order_counts_from_db = batch_query_order_counts(connection, payment_ids_to_check_db, time_window_seconds)

        logger.info(f"准备检查来自 Redis 的 {len(active_payment_ids_with_bank)} 个支付码...")

        for payment_id, bank_name in active_payment_ids_with_bank.items():
            payment_id = int(payment_id)
            order_count = order_counts_from_db.get(payment_id, 0) 
            
            if order_count > 0:
                logger.info(f"支付码 {payment_id} (bank_type_id: {bank_name}) 在过去3天内有 {order_count} 笔订单，跳过清理。")
                continue

            if bank_name is not None:
                redis_key = f'login_off_realtime_{bank_name}_{payment_id}'
                
                rds.set(redis_key, '1', ex=10 * 60) 
                logger.info(f"支付码 {payment_id} (bank_name: {bank_name}) 过去三天没有订单。成功设置 Redis 键 '{redis_key}' (有效期10分钟)。")
            else:
                logger.warning(
                    f"支付码 {payment_id} 过去三天没有订单，但银行 ({bank_name}) "
                    f"无效或未在 LOGIN_ON_MAPPING 中定义，无法设置 'login_off_realtime' 键。"
                )

        logger.info("三天未接单支付码清理完成")

    except Exception as e:
        logger.exception(f"清理三天未接单支付码时发生错误: {e}")

# 主函数
def main():
    try:
        logger.info("初始化 Redis 和 MySQL 连接...")

        # 使用 with 语句管理 MySQL 和 Redis 连接，确保连接自动关闭
        with pymysql.connect(host=conf['mysql_host'],
                             user=conf['mysql_user'],
                             password=conf['mysql_password'],
                             db=conf['mysql_database'],
                             charset='utf8mb4',
                             cursorclass=pymysql.cursors.DictCursor) as connection:

            with redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8') as rds:
                clean_inactive_payments(rds, connection)

    except pymysql.MySQLError as e:
        logger.exception(f"MySQL 连接错误: {e}")
    except redis.RedisError as e:
        logger.exception(f"Redis 连接错误: {e}")
    except Exception as e:
        logger.exception(f"主函数运行出错: {e}")

if __name__ == '__main__':
    main()
