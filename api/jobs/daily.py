import redis
import pymysql
from config import get_config
import logging
from logging.handlers import TimedRotatingFileHandler

LOG_FILE = "daily.log"
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
            sql_select = """select record_type,sum(if(user_type=1,amount,0)) as amount_m,
                                sum(if(user_type=0,amount,0)) as amount_p from balance_record where 
                                date(time_create) = date(date_add(now(),interval -24 hour)) group by record_type"""
            sql_insert = """insert into daily(`date`,`balance_type`,`record_type`,`amount`)
                                                   values (date(date_add(now(),interval -24 hour)),%s,%s,%s)"""
            cur.execute(sql_select)
            r = cur.fetchall()
            for i in r:
                i = dict(i)
                cur.execute(sql_insert, (0, [i['record_type']], i['amount_p']))
                cur.execute(sql_insert, (1, [i['record_type']], i['amount_m']))
        except Exception:
            logging.exception('记录异常')
            connection.rollback()
        else:
            connection.commit()
        finally:
            connection.close()


if __name__ == '__main__':
    main()
