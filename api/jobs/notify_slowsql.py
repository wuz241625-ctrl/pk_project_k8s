import json
import logging
import redis
import requests
import time

from config import get_config
from logging.handlers import TimedRotatingFileHandler

# 日志设置
LOG_FILE = "slow_query_alert_consumer.log"
logger = logging.getLogger()
logger.setLevel(logging.INFO)
fh = TimedRotatingFileHandler(LOG_FILE, when='MIDNIGHT', interval=1, backupCount=15)
datefmt = '%Y-%m-%d %H:%M:%S'
format_str = '%(asctime)s %(levelname)s %(message)s '
formatter = logging.Formatter(format_str, datefmt)
fh.setFormatter(formatter)
logger.addHandler(fh)

# 配置加载
conf = get_config()

def main():
    while True:
        try:
            logger.info('尝试连接 Redis...')
            rds = redis.Redis(
                host=conf['redis_host'],
                port=6379,
                db=0,
                encoding='utf-8',
                decode_responses=True  # 自动 decode
            )
            rds.ping()
            logger.info('成功连接 Redis')
        except Exception:
            logger.exception('连接 Redis 失败，5 秒后重试...')
            time.sleep(5)
            continue

        ps = rds.pubsub()
        try:
            ps.subscribe('slow_query_alerts')
            logger.info('已订阅 slow_query_alerts 频道，开始监听消息...')
        except Exception:
            logger.exception('订阅 Redis 频道失败，5 秒后重试...')
            time.sleep(5)
            continue

        try:
            for i in ps.listen():
                try:
                    rds.ping()
                except Exception:
                    logger.exception("Redis 心跳失败，准备重连...")
                    break  # 跳出 listen 循环，外层重连

                logger.info(f"接收到原始信息: {i}")
                if i['type'] == 'message':
                    logger.info(f"接收到消息: {i}")
                    try:
                        task_json = i['data']
                        logger.info(f"解码后的数据: {task_json}")
                        send_alert(task_json)
                    except Exception:
                        logger.exception('消息处理异常')
                        continue
        except Exception:
            logger.exception('Redis 监听异常，5 秒后重试...')
            time.sleep(5)

# === 发送 Telegram 告警 ===
def send_alert(task_json):
    try:
        task = json.loads(task_json)
    except json.JSONDecodeError:
        logger.exception(f"任务 JSON 解析失败: {task_json}")
        return

    bot_token = task.get("bot_token")
    chat_id = task.get("chat_id")
    text = task.get("text")
    parse_mode = task.get("parse_mode", "Markdown")

    if not (bot_token and chat_id and text):
        logger.warning(f"任务字段不完整: {task}")
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    logger.info(f"准备发送告警到 Telegram: {url}")
    logger.info(f"发送内容: chat_id={chat_id}, text={text}, parse_mode={parse_mode}")

    try:
        response = requests.post(url, data={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode
        }, timeout=10)

        logger.info(f"Telegram 响应状态码: {response.status_code}")
        logger.info(f"Telegram 响应内容: {response.text}")

        if response.status_code == 200:
            logger.info(f"告警已发送: {text[:50]}...")
        elif response.status_code == 429:
            retry_after = response.json().get("parameters", {}).get("retry_after", 5)
            logger.warning(f"被限流，{retry_after}s 后重试")
            time.sleep(retry_after)
        else:
            logger.warning(f"发送失败: {response.status_code} - {response.text}")

    except Exception:
        logger.exception("发送 Telegram 消息失败")

# === 启动入口 ===
if __name__ == '__main__':
    main()