import asyncio
import json
import logging
import redis

from application.app.websocket import app
from application.phonepe import phmonitor
from config import get_config

conf = get_config()


def main(loop):
    asyncio.set_event_loop(loop)
    try:
        rds = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
    except Exception:
        logging.exception('连接redis或数据库错误')
        return
    ps = rds.pubsub()
    ps.subscribe('phonepe_msg')
    for i in ps.listen():
        if i['type'] == 'message':
            try:
                data = json.loads(i['data'])
                data_s = dict(type=data['type'])
                try:
                    # if data['to'] == 'phonepe':
                    #     socket = phmonitor.phonepe_socket[data['id']]
                    # else:
                    socket = app.user_socket[data['id']]
                except Exception as e:
                    logging.info('无目标:{e}, i{i}'.format(e=str(e), i=i))
                    continue
                if data['type'] == 'Start':
                    # app通知监控开始
                    socket.partner_id = data['partner_id']
                    socket.payment_id = data['payment_id']
                    data_s['phone'] = data['phone']
                elif data['type'] == 'my.payment':
                    # 监控通知app开始结果
                    data_s['code'] = data['code']
                elif data['type'] == 'OTP':
                    # app通知监控otp
                    data_s['otp'] = data['otp']

                _types = [
                    'freecharge.login',
                    'freecharge.sendOTP',
                    'phonepe.login',
                    'phonepe.sendOTP',
                    'mobi.login',
                    'mobi.sendOTP',
                    'airtel.login',
                    'airtel.sendOTP',
                ]
                if data['type'] in _types:
                    data_s['status'] = data['status']
                    if data['status'] == 0:  # 删除key
                        _key = 'login_freecharge_{id}'.format(id=data['id'])
                        rds.delete(_key)
                        _key = 'login_phonepe_{id}'.format(id=data['id'])
                        rds.delete(_key)
                        _key = 'login_mobi_{id}'.format(id=data['id'])
                        rds.delete(_key)
                socket.write_message(data_s)
                logging.info('发送正常。' + json.dumps(data_s))
            except Exception as e:
                logging.exception('发送异常:{}'.format(e))
                continue
