import os

dev = dict(
    redis_host='redis',
    mysql_host='mysql',
    mysql_user='root',
    mysql_password='Pass_1234',
    mysql_database='pakistan',
    debug=False,
    autoreload=False,
    pay_url='https://api.aweces.com/api/order/',
    ospay_api_host='http://api.aweces.com/api',
    websocket_api_allow_host=['ospay689.com','api.aweces.com'],
    # pay_url='https://lakshmivip.com/api/order/',
    key_order='g8yvgfdghfdsthkukjbngdRSGHvba56n112',
    secret_key='supw4dqfnmkiuhg4567z54sconfj1d6djp3',
    # usdt_api_endpoint='http://dhd64971.com/api/brave_troops/usdt/remits/place_order',
    usdt_api_endpoint='https://u.dhd64971.com/api/brave_troops/usdt/remits/place_order',
    current_pay='pakistanpay',
    BOT_TOKEN = "8265848669:AAEV132TZEKghCK5PiaZK3CJDHjsv7Fo3U0",
    SQL_TIMEOUT = 6000,
    GROUP_ID = -1002501240556,
    
    # EasyPaisa API 配置
    easypaisa_api_url='http://34.150.42.92:83',
    easypaisa_user_id='ba08c3c0e4f546ad92dd2c2e8542ca36', 
    easypaisa_secret_key='ca45b35e132b46b9b68dd55f1ab077de',
    # jazzcash API 配置
    jazzcash_api_url='http://34.150.42.92:84',
    jazzcash_user_id='ba08c3c0e4f546ad92dd2c2e8542ca36',
    jazzcash_secret_key='ca45b35e132b46b9b68dd55f1ab077de'
)

product = dict(
    redis_host='redis',
    mysql_host='mysql',
    mysql_user='pakistan',
    mysql_password=r'HFCCoB$D7]{?NTNn',
    mysql_database='pakistan',
    debug=False,
    autoreload=False,
    pay_url='https://pgood.vip/api/order/',
    ospay_api_host='http://api.awekay.com/api',
    websocket_api_allow_host=['ospay689.com','api.aweces.com','pgood.vip','cgood.vip','jgood.vip'],
    # pay_url='https://lakshmivip.com/api/order/',
    key_order='g8yvgfdghfdsthkukjbngdRSGHvba56n112',
    secret_key='supw4dqfnmkiuhg4567z54sconfj1d6djp3',
    # usdt_api_endpoint='http://dhd64971.com/api/brave_troops/usdt/remits/place_order',
    usdt_api_endpoint='https://u.dhd64971.com/api/brave_troops/usdt/remits/place_order',
    current_pay='pakistanpay',
    BOT_TOKEN = "8265848669:AAEV132TZEKghCK5PiaZK3CJDHjsv7Fo3U0",
    SQL_TIMEOUT = 6000,
    GROUP_ID = -1002501240556,
    
    # EasyPaisa API 配置
    easypaisa_api_url='http://34.150.42.92:83',
    easypaisa_user_id='ba08c3c0e4f546ad92dd2c2e8542ca36', 
    easypaisa_secret_key='ca45b35e132b46b9b68dd55f1ab077de',
    # jazzcash API 配置
    jazzcash_api_url='http://34.150.42.92:84',
    jazzcash_user_id='ba08c3c0e4f546ad92dd2c2e8542ca36',
    jazzcash_secret_key='ca45b35e132b46b9b68dd55f1ab077de'
)


def get_config():
    env = os.environ.get('RUN_ENV', 'DEV')
    if env == 'DEV':
        return dev
    return product
