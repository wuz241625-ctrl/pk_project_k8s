import datetime
from encodings.utf_8 import decode, encode

import redis
import pymysql
from config import get_config
import logging
from logging.handlers import TimedRotatingFileHandler

LOG_FILE = "balance_report.log"
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

    except Exception as e:
        logging.exception('连接redis或数据库错误')
        return
    with connection.cursor() as cur:
        try:
            logging.info(datetime.datetime.now())
            # 统计余额（商户余额、冻结余额暂不统计id为36、41、192的商户）+ 312
            sql = """insert into balance_count_record (balance_m,balance_m_frozen,balance_p,balance_p_frozen,balance_p_deposit,balance_p_outside,balance_p_frozen_outside,balance_p_inside,balance_p_frozen_inside)
                            select m.balance_m,m.balance_m_frozen,p.balance_p,p.balance_p_frozen,p.balance_p_deposit,balance_p_outside,balance_p_frozen_outside,balance_p_inside,balance_p_frozen_inside from 
                            (select sum(balance) as balance_m, sum(balance_frozen) as balance_m_frozen from merchant where id not in ('196')) as m,
                            (select sum(balance) as balance_p, sum(balance_frozen) as balance_p_frozen, sum(balance_deposit) as balance_p_deposit from partner) as p,
                            ( SELECT sum( balance ) AS balance_p_outside, sum( balance_frozen ) AS balance_p_frozen_outside FROM partner where type =1 ) AS outside,
	                        ( SELECT sum( balance ) AS balance_p_inside, sum( balance_frozen ) AS balance_p_frozen_inside FROM partner where type =0 ) AS inside"""
            cur.execute(sql)
            logging.info(datetime.datetime.now())

        except Exception:
            logging.exception('记录异常')
            connection.rollback()
        else:
            connection.commit()
        finally:
            connection.close()


if __name__ == '__main__':
    main()
