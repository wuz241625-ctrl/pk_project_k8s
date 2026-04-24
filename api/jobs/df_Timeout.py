import datetime
import time
import pymysql
from config import get_config
import logging
from logging.handlers import TimedRotatingFileHandler
import redis

LOG_FILE = "df_timeout.log"
logger = logging.getLogger()
logger.setLevel(logging.INFO)
fh = TimedRotatingFileHandler(LOG_FILE, when='MIDNIGHT', interval=1, backupCount=30)
datefmt = '%Y-%m-%d %H:%M:%S'
format_str = '%(asctime)s %(levelname)s %(message)s '
formatter = logging.Formatter(format_str, datefmt)
fh.setFormatter(formatter)
logger.addHandler(fh)

def dict_to_kv(data):
    """将字典返回 k1,k2,k3...  %s,%s,%s... 和 [val1,val2,val3...]"""
    d = {k: data[k] for k in sorted(data)}
    sql_key = ', '.join(k for k in d.keys())
    sql_place = ', '.join(["%s"] * len(data))
    sql_val = d.values()

    return sql_key, sql_place, sql_val

def issue_timeout(conn, conf):
    rds = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
    with conn.cursor() as cur:
        try:
            now = datetime.datetime.now()
            hours_24_ago = now - datetime.timedelta(hours=48)
            mins_5_ago = now - datetime.timedelta(minutes=30) # 接单之后失效时间
            # 查看代付过期是否开启
            sys_info_sql = "select expired_status_df from sys_info"
            cur.execute(sys_info_sql)
            sys_info = cur.fetchall()
            if sys_info and not sys_info[0]['expired_status_df']:
                logging.info('代付过期开关关闭')
                return
            # 已抢单但是没有付款的超时(代付到第三方的不用过时)
            sql2 = "select code, merchant_id,partner_id from orders_df where status=1 and time_create " \
                  "between %s and %s and %s > time_accept and partner_id not in (select id from partner where type=0) and otherpay_id is null and otherpay is null"
            # 订单状态修改
            _order_status = "update orders_df set status = 0, partner_id = null, payment_id = null, payment_img = 0, time_accept = null, time_payed = null, time_success = null where code=%s and status=1"

            # 对已抢单但是没有付款的超时，直接将订单状态退回公池
            cur.execute(sql2, (hours_24_ago, now, mins_5_ago))
            r2 = cur.fetchall()
            for i in r2:
                # 获取锁，10秒内锁定
                busy_key = 'grab_df_{}'.format(i['code'])
                code_lock = rds.setnx(busy_key, 1)
                if not code_lock:
                    continue
                rds.expire(busy_key, 10)
                if not cur.execute(_order_status, (i['code'])):
                    logging.error('代付已接单状态过期退回公池失败 %s %s %s' % (i['code'], i['merchant_id'] ,i['partner_id']))
                    rds.delete(busy_key)
                    continue
                rds.delete(busy_key)
                logging.info('代付已接单状态过期退回公池成功{code}，{merchant_id},{partner_id}'.format(code=i['code'], merchant_id=i['merchant_id'], partner_id=i['partner_id']))
        except Exception as e:
            logging.error('代付已接单状态过期退回公池 出错{e}'.format(e=e))
            conn.rollback()
        else:
            conn.commit()
        finally:
            conn.close()


def main():
    conf = get_config()
    connection = pymysql.connect(
        host=conf.get('mysql_host', 'localhost'),
        port=conf.get('port', 3306),
        user=conf['mysql_user'],
        password=conf['mysql_password'],
        db=conf['mysql_database'],
        charset=conf.get('charset', 'utf8'),
        autocommit=conf.get('autocommit', False),
        cursorclass=pymysql.cursors.DictCursor
    )
    issue_timeout(connection, conf)


if __name__ == '__main__':
    # for i in range(2):
    #     if i == 0:
    #         logging.info('开始执行代付接单过期退回公池')
    #     main()
    #     time.sleep(30)
    logging.info('开始执行代付接单过期退回公池')
    main()
    logging.info('结束执行代付接单过期退回公池')
