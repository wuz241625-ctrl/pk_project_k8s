import json

import redis
import pymysql
from config import get_config
import logging
from logging.handlers import TimedRotatingFileHandler
import sys
import os
# 将项目的主目录添加进系统path，才能直接调用application文件夹下面的模块等
parent_directory = os.path.dirname(__file__)
grandparent_directory = os.path.dirname(parent_directory)
sys.path.append(grandparent_directory)
from application.third.thirdPart_df import AGDF, cubpay, wallet, haoda, happypay, kingpay, razo, ydpay, sdpay, queen, inpay, redpay, lucky, apay, globe, rupix, pay58pay, kuaiyin, wepay, lemonpay, pay777pay, swiftpay, lemonpay2, quickpay, snakepay, hkpay, skpay, catspay, lemonpay3, pay188pay, tatapay, ospay, vibrapay,qqpay, marspay, Gamepayer

# 用于批量处理发送到三方代付的订单
LOG_FILE = "batch_Thirdpay_df.log"
logger = logging.getLogger()
logger.setLevel(logging.INFO)
fh = TimedRotatingFileHandler(LOG_FILE, when='MIDNIGHT', interval=1, backupCount=15)
datefmt = '%Y-%m-%d %H:%M:%S'
format_str = '%(asctime)s %(levelname)s %(message)s '
formatter = logging.Formatter(format_str, datefmt)
fh.setFormatter(formatter)
logger.addHandler(fh)
conf = get_config()


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
    ps = rds.pubsub()
    ps.subscribe('batch_Thirdpay_df')
    for i in ps.listen():
        if i['type'] == 'message':
            try:
                logging.info('收到订单: %s' % i['data'])
                id = i['data'].decode().split('_')[0]
                code = i['data'].decode().split('_', 1)[1]
                logging.info(f"Extracted code: {code}")
                connection.ping()
                with connection.cursor() as cur:
                    # 查找三方代付
                    sql = 'select id,mer_id,mer_key,mer_key2,mer_key3,pay_url,pay_name,pay_name_zh,status from third_pay_df where id = %s'
                    cur.execute(sql, id)
                    r_third = cur.fetchall()
                    # connection.commit()

                    if not r_third:
                        logging.info('订单: %s , 三方代付不存在' % i['data'])
                        connection.rollback()
                        continue
                    r_third = r_third[0]
                    if not r_third['status'] == 1:
                        logging.info('订单: %s , %s 三方代付未激活' % (i['data'], r_third['pay_name_zh']))
                        connection.rollback()
                        continue

                    # 获取锁，50秒内锁定
                    busy_key = 'grab_df_{}'.format(code)
                    code_lock = rds.setnx(busy_key, 1)
                    if not code_lock:
                        logging.info('订单: %s , 未抢到锁，已有人在操作' % i['data'])
                        continue
                    rds.expire(busy_key, 50)

                    # 查找订单
                    sql = 'select * from orders_df where code = %s'
                    cur.execute(sql, code)
                    code_info = cur.fetchall()
                    if not code_info:
                        logging.info('订单: %s , 不存在' % i['data'])
                        connection.rollback()
                        rds.delete(busy_key)
                        continue
                    code_info = code_info[0]
                    if code_info['is_split'] == 1:
                        logging.info('订单: %s , 已经有人在拆单操作了' % i['data'])
                        connection.rollback()
                        rds.delete(busy_key)
                        continue
                    if not code_info['status'] == 0:
                        # if int(code_info['payment_id']) != 502246 and int(id) != 74: 
                        #     logging.info('订单: %s , 已经有人在操作了' % i['data'])
                        #     connection.rollback()
                        #     rds.delete(busy_key)
                        #     continue
                        payment_id = code_info['payment_id']
                        # 简单检查并确保 payment_id 和 id 都不为 None
                        if payment_id and id:
                            if int(payment_id) != 502246 and int(id) != 74:
                                logging.info('订单: %s , 已经有人在操作了' % i['data'])
                                connection.rollback()
                                rds.delete(busy_key)
                                continue
                        else:
                            if payment_id is None:
                                logging.error("订单: %s , payment_id 为 None" % i['data'])
                                rds.delete(busy_key)
                                continue
                            if id is None:
                                logging.error("订单: %s , id 为 None" % i['data'])
                                rds.delete(busy_key)
                                continue
                        # 20250302 追加
                        rds.delete(busy_key)
                        continue

                    # 开始去第三方代付
                    if r_third['pay_name'] == 'AGDF':
                        if not AGDF(rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'],r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'cubpay':
                        if not cubpay(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'],r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'wallet':
                        if not wallet(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'],r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] in ['haoda', 'haoda2', 'haoda3']:  # 如有其他账号，在列表中增加
                        if not haoda(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url'], r_third['mer_key2']):

                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'happypay':
                        if not happypay(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'happypay':
                        if not happypay(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'kingpay':
                        if not kingpay(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url'], r_third['mer_key3'], "/df_notice/kingpay"):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'kingpay2':
                        if not kingpay(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url'], r_third['mer_key3'], "/df_notice/kingpay2"):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] in ['razo', 'razo2', 'razo3', 'razo4']:  # 如有其他账号，在列表中增加
                        if not razo(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url'], r_third['mer_key2']):

                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'ydpay':
                        if not ydpay(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url'], r_third['mer_key2']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'sdpay':
                        if not sdpay(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'queen':
                        if not queen(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'],
                                     r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'inpay':
                        if not inpay(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'redpay':
                        if not redpay(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'lucky':
                        if not lucky(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'apay':
                        if not apay(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'globe':
                        if not globe(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'rupix':
                        if not rupix(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == '58pay':
                        if not pay58pay(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'kuaiyin':
                        if not kuaiyin(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'wepay':
                        if not wepay(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'lemonpay':
                        if not lemonpay(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'pay777pay':
                        if not pay777pay(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'swiftpay':
                        if not swiftpay(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['mer_key2'], r_third['mer_key3'], r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'lemonpay2':
                        if not lemonpay2(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['mer_key2'], r_third['mer_key3'], r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'quickpay':
                        if not quickpay(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key3'], r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'snakepay':
                        if not snakepay(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'hkpay':
                        if not hkpay(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'skpay':
                        if not skpay(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url'], r_third['mer_key3']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'catspay':
                        if not catspay(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'lemonpay3':
                        if not lemonpay3(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == '188pay':
                        if not pay188pay(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] in ['OSPAY', 'OSPAY_UPI', '789pay_upi', '789pay']:
                        if not ospay(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'TataPay':
                        if not tatapay(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'VibraPay':
                        if not vibrapay(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url'], r_third['mer_key2']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'qqpay':
                        if not qqpay(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'marspay':
                        if not marspay(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    elif r_third['pay_name'] == 'gamepayer':
                        if not Gamepayer(cur, rds, logging, code_info, r_third['mer_id'], r_third['mer_key'], r_third['pay_url']):
                            connection.rollback()
                            logging.info('订单: %s ,三方代付 %s 请求失败' % (i['data'], r_third['pay_name_zh']))
                            rds.delete(busy_key)
                            continue
                    else:
                        connection.rollback()
                        rds.delete(busy_key)
                        logging.error('订单: %s ,三方代付 %s 无此 pay_name' % (i['data'], r_third['pay_name_zh']))
                        continue
                    sql = "update orders_df set otherpay_id=%s,otherpay=%s,status=1,partner_id=null,payment_id=null,earn_system=null,time_payed=null,payment_img=0,time_accept=NOW() where code=%s"
                    ret = cur.execute(sql, (id, r_third['pay_name_zh'], code))
                    if not ret:
                        logging.info('订单: %s ,三方代付 %s 修改订单失败' % (i['data'], r_third['pay_name_zh']))
                        connection.rollback()
                        rds.delete(busy_key)
                    else:
                        connection.commit()
                        rds.delete(busy_key)
                        logging.info('订单: %s ,三方代付 %s 订单创建成功' % (i['data'], r_third['pay_name_zh']))
            except Exception as e:
                logging.exception('派单异常:{e}'.format(e=e))


if __name__ == '__main__':
    main()
