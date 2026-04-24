import datetime
import hashlib
import os
import time

import redis
import pymysql
import requests

from encodings.utf_8 import decode, encode

from config import get_config
import logging
from logging.handlers import TimedRotatingFileHandler

# 自动生成进程ID（使用进程PID）
WORKER_ID = os.getpid()
# 为每个进程创建独立的日志文件
LOG_FILE = f"order_df_notify_{WORKER_ID}.log"
logger = logging.getLogger()
logger.setLevel(logging.INFO)
fh = TimedRotatingFileHandler(LOG_FILE, when='MIDNIGHT', interval=1, backupCount=15)
datefmt = '%Y-%m-%d %H:%M:%S'
format_str = '%(asctime)s %(levelname)s %(message)s '
formatter = logging.Formatter(format_str, datefmt)
fh.setFormatter(formatter)
logger.addHandler(fh)
conf = get_config()


class SignatureAndVerification(object):
    """MD5签名和验签"""

    @classmethod
    def data_processing(cls, data):
        """
        :param data: 需要签名的数据，字典类型
        :return: 处理后的字符串，格式为：参数名称=参数值，并用&连接
        """
        if "sign" in data:
            del data["sign"]
        if "sign_type" in data:
            del data["sign_type"]
        dataList = []
        for key in sorted(data):
            if data[key]:
                dataList.append("%s=%s" % (key, data[key]))
        return "&".join(dataList).strip()

    @classmethod
    def md5_sign(cls, data, api_key):
        """
        MD5签名
        :param api_key: MD5签名需要的字符串
        :return: 签名后的字符串sign
        """
        data = cls.data_processing(data) + "&key=" + api_key.strip()
        md5 = hashlib.md5()
        md5.update(data.encode(encoding='UTF-8'))
        r = md5.hexdigest().upper()
        return r


def main():
    try:
        connection = pymysql.connect(host=conf['mysql_host'],
                                     user=conf['mysql_user'],
                                     password=conf['mysql_password'],
                                     db=conf['mysql_database'],
                                     charset='utf8mb4',
                                     cursorclass=pymysql.cursors.DictCursor)
        rds = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')

    except Exception:
        logging.exception('连接redis或数据库错误')
        return
    sql_select = """select code,merchant_code,merchant_id,amount,realpay,notify,o.status,o.utr,time_updated,mc_key,parent_id from 
                            orders_df o,merchant m  where code=%s and m.id = merchant_id limit 1"""
    sql_update = """update orders_df set status=%s where code=%s and status=%s limit 1"""
    ps = rds.pubsub()
    ps.subscribe('order_df_notify')
    fail_order = None
    for i in ps.listen():
        if i['type'] == 'message':
            code = i['data'].decode()
            # 重复二次回调时，暂停1秒
            if fail_order == code:
                time.sleep(1)
            try:
                # 使用Redis分布式锁确保同一订单只被一个进程处理
                lock_key = f"lock_df_notify_{code}"
                # 尝试获取锁，15秒过期时间
                lock_acquired = rds.set(lock_key, WORKER_ID, nx=True, ex=15)
                if not lock_acquired:
                    logging.info(f'Worker-{WORKER_ID} 订单 {code} 已被其他进程处理，跳过')
                    continue
                logging.info(f'Worker-{WORKER_ID} 订单 {code} 处理')
                with connection.cursor() as cur:
                    connection.ping()
                    cur.execute(sql_select, code)
                    order = dict((cur.fetchall())[0])
                    connection.commit()
                    if order['status'] not in [-2, 3]:
                        continue
                    # 回调
                    data = dict()
                    data['mer_id'] = order['merchant_id']
                    data['order_id'] = order['merchant_code']
                    data['status'] = 'ok' if order['status'] == 3 else 'error'
                    data['amount'] = order['amount']
                    data['realpay'] = order['realpay']
                    data['reason'] = 'ok' if order['status'] == 3 else 'error'
                    dt = SignatureAndVerification.md5_sign(data, order['mc_key'])
                    data['sign'] = dt

                    #  SET df_notify_merchant_ids "1,2,3,4"
                    redis_key = 'df_notify_merchant_ids'
                    logger.info(f"开始获取 Redis 键: {redis_key}")

                    merchant_ids_bytes = rds.get(redis_key) 
                    logger.info(f"Redis 返回的原始数据 (bytes): {merchant_ids_bytes}")

                    if isinstance(merchant_ids_bytes, bytes):
                        merchant_ids_str = merchant_ids_bytes.decode()
                        logger.info(f"数据解码为字符串: {merchant_ids_str}")
                    else:
                        merchant_ids_str = ""
                        logger.info("Redis 键不存在或值为空/非 bytes 类型，字符串初始化为空。")

                    merchant_ids_str = merchant_ids_str.strip() if merchant_ids_str else ""
                    logger.info(f"清理前后空白后的字符串: '{merchant_ids_str}'")

                    merchant_id_list = [mid.strip() for mid in merchant_ids_str.split(',') if mid.strip()]
                    logger.info(f"解析后的商户 ID 列表: {merchant_id_list}")

                    current_merchant_id = str(order['merchant_id'])
                    logger.info(f"当前订单商户 ID: {current_merchant_id}")

                    if current_merchant_id in merchant_id_list:
                        logger.info("商户 ID 匹配成功，继续检查 UTR。")
                        if order['utr']: 
                            utr_value = str(order['utr'])
                            data['utr'] = utr_value
                            logger.info(f"订单包含 UTR，赋值 data['utr'] = {utr_value}")
                        else:
                            data['utr'] = ''
                            logger.info("订单 UTR 字段为空或不存在，赋值 data['utr'] = ''")
                    else:
                        logger.info("商户 ID 未匹配，跳过 UTR 赋值。")
                    
                    url = order['notify']
                    parent_id = order.get('parent_id', '')
                    try:
                        rstr = 'ok'
                        if (not url == 'sys') and (not parent_id):
                            logging.info('{code},回调url={url},参数{result}'.format(code=code, url=url, result=data))
                            r = requests.post(url, data, timeout=10, verify=False)
                            rs = r.text.lower()
                            try:
                                rstr = rs.decode()
                            except Exception:
                                rstr = rs
                        # 通知成功
                        if rstr == 'ok':
                            try:
                                cur.execute(sql_update, (4 if order['status'] == 3 else -1, code, order['status']))
                                connection.commit()
                                logging.info('Worker-{} 回调成功{}'.format(WORKER_ID, code))
                            except Exception:
                                logging.exception('Worker-{} 订单更新失败{}'.format(WORKER_ID, code))
                            if fail_order == code:
                                fail_order = None
                        else:
                            logging.warning('Worker-{} 返回异常结果{}:{}'.format(WORKER_ID, code, r.text))
                            fail_order = order_df_notify_fail(rds, order, fail_order)
                        if (not url == 'sys') and (not parent_id):
                            r.close()
                            del r
                    except Exception as e:
                        logging.exception('Worker-{} {}回调异常{}'.format(WORKER_ID, code, e))
                        fail_order = order_df_notify_fail(rds, order, fail_order)
            except Exception:
                logging.exception('Worker-{} 回调异常'.format(WORKER_ID))
                continue


# 代付回调失败
def order_df_notify_fail(rds, order, fail_order):
    code = order['code']
    if datetime.datetime.now() > order['time_updated'] + datetime.timedelta(minutes=5):
        logging.info('超时{order}'.format(order=code))
        return None if fail_order == code else fail_order
    else:
        rds.publish('order_df_notify', code)
        return fail_order if fail_order else code


if __name__ == '__main__':
    main()
