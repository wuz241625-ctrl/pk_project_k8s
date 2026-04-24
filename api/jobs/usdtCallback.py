import time
from datetime import datetime, timedelta
from decimal import Decimal
import json
import redis
import pymysql
import logging
from logging.handlers import TimedRotatingFileHandler
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from config import get_config

# 用于usdt订单回调
LOG_FILE = "usdtCallback.log"
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
        rds = redis.Redis(host=conf['redis_host'], port=6379, db=0, decode_responses=True, encoding='utf-8')
        match_usdtOrder(connection, rds)
    except Exception as e:
        logging.exception('连接redis或数据库错误', e)
        return

def match_usdtOrder(connection, rds):
    with connection.cursor() as cursor:
        try:
            # 获取40分钟内的订单，按时间升序，订单、时间、金额三种类别分别按逗号隔开，按usdt地址来循环查询账单
            time_scope = str(datetime.now() - timedelta(minutes=40))
            usdtorders_select = """SELECT address, GROUP_CONCAT(serial_number) AS serial_number, GROUP_CONCAT(created_at ORDER BY created_at ASC) AS created_ats, GROUP_CONCAT(usdt_amount) AS usdt_amount FROM usdt_deposit_orders WHERE status = 1 AND created_at >= %s GROUP BY address ORDER BY created_at ASC"""
            if not cursor.execute(usdtorders_select, (time_scope,)):
                connection.rollback()
            usdt_orders = cursor.fetchall()
            # print(usdt_orders)
            matched_orders = []
            for usdt_order in usdt_orders:
                first_created_ats = usdt_order['created_ats']
                first_created_at = first_created_ats.split(',')[0] # 按第一个时间来查询，这个是最低的时间
                first_created_at_timestamp = int(datetime.strptime(first_created_at, "%Y-%m-%d %H:%M:%S").timestamp())*1000
                user_address = usdt_order['address']
                # api_endpoint = f"https://apilist.tronscanapi.com/api/new/token_trc20/transfers?limit=100&contract_address=TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t&start_timestamp={first_created_at_timestamp}&confirm=true&filterTokenValue=1&toAddress={user_address}"   # tronscan的接口很多时候接口返回的数据是有延迟的
                api_endpoint = f"https://api.trongrid.io/v1/accounts/{user_address}/transactions/trc20?only_confirmed=true&min_timestamp={first_created_at_timestamp}&contract_address=TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t&only_to=true&limit=50"  # tron network 接口
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) '
                                  'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 '
                                  'UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 '
                                  'NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) '
                                  'AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
                    # 'TRON-PRO-API-KEY':'de794edc-a284-4ab6-a171-294eb89f50b2', # tronscan 接口
                    'TRON-PRO-API-KEY':'fe293421-6f83-4988-a4f9-87925d538753' # tron network 接口
                }
                session = requests.Session()
                session.mount('http://', HTTPAdapter(max_retries=Retry(total=2)))
                session.mount('https://', HTTPAdapter(max_retries=Retry(total=2)))
                logger.info('{api_endpoint} {user_address} usdt request'.format(user_address=user_address, api_endpoint=api_endpoint))
                try:
                    response = session.get(api_endpoint, headers=headers, timeout=(30, 30), verify=False)
                    logger.info('{} usdt response {}'.format(user_address, response.text))
                    data = json.loads(response.text)
                except Exception as e:
                    logger.error('{api_endpoint} {user_address} usdt request error'.format(api_endpoint=api_endpoint, user_address=user_address))
                    logger.error(e)
                transactions = data.get('data', [])
                if not transactions or len(transactions) == 0:
                    logger.info('{} usdt No data'.format(user_address))
                    time.sleep(1)
                    continue

                # 有帳單（total不為0）再解析訂單
                usdt_amounts = usdt_order['usdt_amount'].split(',')
                usdt_serial_numbers = usdt_order['serial_number'].split(',')
                usdt_created_ats = usdt_order['created_ats'].split(',')
                for transaction in transactions:
                    # 判斷每個transaction為有效的紀錄 contractRet == 'SUCCESS' confirmed采集到有些是false的
                    # contractRet = transaction.get('contractRet')
                    # confirmed = transaction.get('confirmed')
                    # if not contractRet == 'SUCCESS' or not confirmed is True: # 必须判断 confirmed 是否是true
                    #     logger.error('账单地址{to_address},账单confirmed 不是 true {transaction}'.format(to_address=transaction['to_address'],  transaction=transaction))
                    #     continue
                    transaction_id = transaction['transaction_id']
                    # 先比對usdt_order跟帳單地址
                    if not user_address == transaction['to']:
                        logger.error('订单地址{usdt_address}, 账单地址{to_address} 不匹配'.format(usdt_address=user_address,  to_address=transaction['to']))
                        continue
                     # 拿著帳單的金額比對key
                    unique_key = 'usdt_' + transaction['to'] + '_' + str(round(Decimal(transaction['value']) / 10 ** 6, 4))
                    usdt_order_serial_number = rds.get(unique_key)
                    # 檢測是否有key 用key的值(serial_number)找订单 再由订单找created_at 比对时间顺序 账单须晚于订单创建时间
                    if not usdt_order_serial_number:
                        logger.error('此账单{unique_key}未匹配到订单金额'.format(unique_key=unique_key))
                        continue
                    try:
                        index = usdt_serial_numbers.index(usdt_order_serial_number)
                        usdt_amount = usdt_amounts[index]
                        usdt_created_at = usdt_created_ats[index]
                    except Exception as e:
                        logger.error('帳单地址{to_address},获取订单错误'.format(to_address=transaction['to']))
                        logger.error(e)
                        continue
                    usdt_timestamp = int(datetime.strptime(usdt_created_at, "%Y-%m-%d %H:%M:%S").timestamp())*1000
                    if not usdt_timestamp < transaction['block_timestamp']:
                        logger.error('错误 订单地址{address}, 订单创建時間{usdt_created_at} 须小于 区块时间{block_timestamp}'.format(address=usdt_order['address'], usdt_created_at=usdt_created_at, block_timestamp=transaction['block_timestamp']))
                        continue
                    logger.info('账单{unique_key}匹配到订单{code}'.format(unique_key=unique_key,code=usdt_order_serial_number))

                    # TODO callback
                    url = 'http://ospay689.com/api/v1/usdt/brave_troops/order/paid'
                    # url = 'http://127.0.0.1:9000/v1/usdt/brave_troops/order/paid'
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) '
                                      'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 '
                                      'UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 '
                                      'NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) '
                                      'AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
                    }
                    try:
                        session = requests.Session()
                        session.mount('http://', HTTPAdapter(max_retries=Retry(total=5)))
                        session.mount('https://', HTTPAdapter(max_retries=Retry(total=5)))
                        data_post = dict()
                        data_post['transaction_id'] = transaction_id
                        data_post['serial_number'] = usdt_order_serial_number
                        data_post['paid_at'] = datetime.fromtimestamp(int(transaction['block_timestamp'])/1000).strftime("%Y-%m-%d %H:%M:%S")
                        logging.info('usdt callback 订单-{code}-发送地址{url},发送{data_post}'.format(code=usdt_order_serial_number, url=url, data_post=data_post))
                        r = requests.post(url, data=data_post, headers=headers, timeout=(5, 10))
                        logging.info('usdt callback-{code}-发送地址{url},发送{data_post},结果{ret}'.format(code=usdt_order_serial_number, url=url, data_post=data_post, ret=r.text))
                        ret = json.loads(r.text)
                    except Exception as e:
                        logger.error('{} callback error'.format(usdt_order_serial_number))
                        logger.error(e)
                        continue
                    if ret['success'] is True:
                        logging.info('usdt callback-{code}-成功'.format(code=usdt_order_serial_number))
                        # 删除占用的金额的key
                        rds.delete(unique_key)
                    else:
                        logging.error('usdt callback-{code}-失败'.format(code=usdt_order_serial_number))
        except Exception as e:
            logging.exception('no order created within 40 mins', e)
            return
        finally:
            cursor.close()

    return matched_orders


if __name__ == '__main__':
    logging.info('开始执行usdt回调')
    main()
    logging.info('结束执行usdt回调')