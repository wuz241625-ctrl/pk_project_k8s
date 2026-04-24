import os

dev = dict(
    redis_host='redis',
    mysql_host='mysql',
    mysql_user='root',
    mysql_password='Pass_1234',
    mysql_database='pakistan',
    debug=False,
    api_url='http://api:9000',
    cookie_key='580627e7a6d547bb83bd8aaa4da4b22b',
    id_token_key='2e05364f510a4dc6a9b760711d8465b4',
    robotApi = 'https://ospay03-02.789pay.one'
)

product = dict(
    redis_host='redis',
    mysql_host='mysql',
    mysql_user='root',
    mysql_password='Pass_1234',
    mysql_database='pakistan',
    debug=False,
    # api_url='https://ospay.vip/api',
    api_url='http://ospay689.com/api',
    cookie_key='5806gfmdkaslgn7897r45383bd8aaa4da4b22b',
    id_token_key='2e053fdsfeuu7g4a9b760711d8465b4',
    BOT_TOKEN = "8265848669:AAEV132TZEKghCK5PiaZK3CJDHjsv7Fo3U0",
    SQL_TIMEOUT = 3000,
    GROUP_ID = -1002501240556,
    robotApi = 'https://pakistan01.789pay.one'
)


def get_config():
    env = os.environ.get('RUN_ENV', 'DEV')
    if env == 'DEV':
        return dev
    return product
