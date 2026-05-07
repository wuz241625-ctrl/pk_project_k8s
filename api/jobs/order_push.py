import datetime
import time
from decimal import Decimal

import redis
import pymysql

from application.payment_eligibility import can_dispatch_df
from config import get_config
import logging
from logging.handlers import TimedRotatingFileHandler

LOG_FILE = "order_push.log"
logger = logging.getLogger()
logger.setLevel(logging.INFO)
fh = TimedRotatingFileHandler(LOG_FILE, when='MIDNIGHT', interval=1, backupCount=15)
datefmt = '%Y-%m-%d %H:%M:%S'
format_str = '%(asctime)s %(levelname)s %(message)s '
formatter = logging.Formatter(format_str, datefmt)
fh.setFormatter(formatter)
logger.addHandler(fh)
conf = get_config()


def _is_easypaisa_payment(payment):
    return (
        str(payment.get('bank_type_id') or '') == '97'
        or str(payment.get('bank_type') or '') == '97'
    )


def _is_jazzcash_payment(payment):
    return (
        str(payment.get('bank_type_id') or '') == '98'
        or str(payment.get('bank_type') or '') == '98'
    )


def _df_order_online(rds, payment):
    payment_id = payment.get('id')
    if _is_easypaisa_payment(payment):
        return can_dispatch_df(payment)
    return rds.sismember('payment_online_df', payment_id)


def _requeue_df_if_online(rds, payment):
    payment_id = payment.get('id')
    if _is_easypaisa_payment(payment):
        if not can_dispatch_df(payment):
            rds.lrem('payment_active_df', 0, payment_id)
            return False
        rds.lrem('payment_active_df', 0, payment_id)
        rds.rpush('payment_active_df', payment_id)
        return True
    if not rds.sismember('payment_online_df', payment_id):
        rds.lrem('payment_active_df', 0, payment_id)
        return False
    rds.lrem('payment_active_df', 0, payment_id)
    rds.rpush('payment_active_df', payment_id)
    return True


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
    sql_select = """select id from orders_df where code=%s and status=0 limit 1"""
    sql_select_payment = """select b.id, b.status, b.certified, b.manual_status, b.bank_type, b.bank_type_id, b.payout_status, partner_id, p.status as partner_status, df_min, df_max from payment b left join partner p on
        p.id=b.partner_id and p.status=1 left join vip v on v.vip=p.vip where b.certified=1 and b.status=1 and b.id=%s"""
    sql_update = """update orders_df set status=1,partner_id=%s,payment_id=%s,time_accept=%s where code=%s and status=0"""
    ps = rds.pubsub()
    ps.subscribe('order_df_push')
    for i in ps.listen():
        if i['type'] == 'message':
            try:
                logging.info('收到订单: %s' % i['data'])
                code = i['data'].decode().split('_')[0]
                amount = Decimal(i['data'].decode().split('_')[1])
                # 查找码商
                list_name = 'payment_active_df'
                back_key = []  # 重新加入list的key
                connection.ping()
                with connection.cursor() as cur:
                    if not cur.execute(sql_select, code):
                        continue
                    payment = None
                    while True:
                        payment_id = rds.lpop(list_name)
                        try:
                            if payment_id is None:
                                break

                            cur.execute(sql_select_payment, payment_id)
                            rows = cur.fetchall()
                            connection.commit()

                            # 没有码商
                            if not rows:
                                continue
                            _payment = dict(rows[0])

                            if not _df_order_online(rds, _payment):
                                rds.lrem('payment_active_df', 0, payment_id)
                                continue

                            # 金额不符
                            if amount < _payment['df_min'] or amount > _payment['df_max']:
                                back_key.append(_payment)
                                continue

                            # 已有订单
                            sql = """select * from orders_df where payment_id=%s and status in (1,2) limit 1"""
                            if cur.execute(sql, payment_id):
                                continue
                            payment = _payment
                            break
                        except Exception:
                            continue
                    for j in back_key:
                        _requeue_df_if_online(rds, j)
                    # 更新订单码商及状态
                    if payment:
                        cur.execute(sql_update, (payment['partner_id'], payment_id, datetime.datetime.now(), code))
                        connection.commit()
                        logging.info('派单: {},卡{}'.format(i['data'], payment_id))
                    else:
                        time.sleep(1)
                        logging.info('等待派单: %s' % i['data'])
                        rds.publish('order_df_push', i['data'].decode('utf8'))
            except Exception as e:
                logging.exception('派单异常:{e}'.format(e=e))


if __name__ == '__main__':
    main()
