import decimal
import hashlib
import json
from datetime import datetime
from decimal import Decimal

from aiomysql import DictCursor
from tornado import websocket
from tornado.ioloop import IOLoop

from application.base import BaseHandler, RewriteJsonEncoder
import bcrypt

from application.message import msg
from application.websocket import bank_analysis, callback


def _is_easypaisa_payment(payment):
    return (
        str((payment or {}).get('bank_type_id') or '') == '97'
        or str((payment or {}).get('bank_type') or '') == '97'
    )


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class Websocket(BaseHandler, websocket.WebSocketHandler):

    def check_origin(self, origin):
        return True

    def open(self):
        self.logger.info('ws connect')
        self.qr_id = None
    def on_close(self):
        self.logger.info('ws close {qr_id}'.format(qr_id=self.qr_id))
        if self.qr_id:
            IOLoop.current().add_callback(self.qrcode_online, 0, None)

    async def on_message(self, message):
        try:
            data = json.loads(message)
            if data['type'] == 'Login':
                return await self.write_message(await self.login(data['admin_id'], data['admin_pw'], data['qr_id'], data.get('login_uuid', None)))
            if data['type'] == 'Online':
                return await self.write_message(await self.qrcode_online(data['online'], data['o_type']))
            if data['type'] == 'New':
                return await self.write_message(await self.new_record(data))
            if data['type'] == 'updateBalance':
                await self.update_result('payment', {'balance': data['balance']}, {'id': self.qr_id})
                # sys_balance = (await self.get_result_by_condition('payment', ['sys_balance'], {'id': self.qr_id}))['sys_balance']
                # if sys_balance != Decimal(data['balance']):
                #     await self.redis.srem('payment_online_ds', self.qr_id)
                #     await self.redis.srem('payment_online_df', self.qr_id)
                #     return await self.write_message(dict(code=99, msg='Balance error'))
            if data['type'] == 'OrderList':
                data_r = await self.get_result_by_condition('payment', ['sys_balance'], {'id': self.qr_id})
                sql = """select sum(amount) as amount from orders_ds where payment_id=%s and status in (3,4) and time_create > curdate()"""
                data_r['ds_balance'] = (await self.query(sql, self.qr_id))[0]['amount']
                sql = """select code,amount,payment_account,payment_name,ifsc from orders_df where payment_id=%s and 
                                            status in (1,2)"""
                data_r['order_list'] = await self.query(sql, self.qr_id)
                return await self.write_message(json.dumps(dict(code=202, data=data_r), cls=RewriteJsonEncoder))
            if data['type'] == 'Getorder':
                return await self.write_message(json.dumps(await self.get_order(data['code'])))
            if data['type'] == 'Cancelorder':
                return await self.write_message(json.dumps(await self.cancel_order(data['code'])))
            if data['type'] == 'CheckLogin':
                current_login_uuid = await self.redis.hget('login_uuid', data['qr_id'])
                if data['login_uuid'] != current_login_uuid:
                    return await self.write_message(
                        json.dumps({'code': 401, 'data': None, 'message': 'Please log in.'}))
        except Exception as e:
            self.logger.exception(e)
            ret = dict(code=99, msg='data error.')
            await self.write_message(json.dumps(ret))

    # 登录
    async def login(self, admin_id, admin_pw, qr_id, login_uuid=None):
        admin = await self.get_result_by_condition('admin', ['id', 'status', 'hash_login'], {'account': admin_id})
        if not admin:
            return dict(code=99, msg='ID or PW Incorrect')

        if not admin['status']:
            return dict(code=99, msg='Account is locked')

        if not bcrypt.checkpw(admin_pw.encode('utf8'), admin['hash_login'].encode('utf8')):
            return dict(code=99, msg='ID or PW Incorrect')

        self.current_user = admin
        self.qr_id = qr_id

        # 密码存于redis 用于接受回调验证时 验证签名
        await self.redis.set('qrcode_key_{id}'.format(id=qr_id), admin_pw)

        data = dict()
        # 返回码信息
        keys = ['bank_type', 'account_type', 'net_id', 'net_pw', 'net_trade_pw', 'phone', 'status', 'partner_id', 'balance_limit', 'channel']
        bank = await self.get_result_by_condition('payment', keys, {'id': qr_id})
        # 返回银行信息
        data['banks'] = await self.get_results_no_condition('bank_type', ['*'])
        if not bank:
            return dict(code=99, msg='QR does not exist')
        self.partner_id = bank['partner_id']

        if not bank['status']:
            return dict(code=99, msg='QR is not activated')
        # self.qr_channel = 1002 if bank['account_type'] == 2 else 1001
        self.qr_channel = bank['channel']
        bank['balance_limit'] = float(bank['balance_limit'])
        data['bank'] = bank
        self.logger.info('监控登录:admin:{admin}, qr_id:{qr_id}'.format(admin=admin_id, qr_id=qr_id))
        # 放置在hash中
        if qr_id and login_uuid:
            await self.redis.hset('login_uuid', qr_id, login_uuid)

        return dict(code=200, msg='Login success.', data=json.dumps(data))

    # 在线状态
    async def qrcode_online(self, online, _type):
        if online:
            bank = await self.get_result_by_condition(
                'payment',
                [
                    'certified',
                    'manual_status',
                    'status',
                    'channel',
                    'bank_type',
                    'bank_type_id',
                    'collection_status',
                    'payout_status',
                ],
                {'id': self.qr_id}
            )
            self.qr_channels = bank['channel'].split(',')
            self.logger.info(f"QR channels for qr_id={self.qr_id}: {self.qr_channels}")
            if str(bank.get('certified')) == '1':
                if _type == 'ds':
                    if _is_easypaisa_payment(bank):
                        ds_enabled = _as_int(bank.get('collection_status')) == 1
                        self.logger.info(
                            "EasyPaisa monitor Online(ds) 已退役为只读: payment_id=%s collection_status=%s",
                            self.qr_id,
                            bank.get('collection_status'),
                        )
                        if not ds_enabled:
                            return dict(code=201, msg='On Fail.', data=json.dumps({'status': 0, 'type': _type}))
                    else:
                        # 非 EP 通道：保留原 legacy 写入
                        await self.redis.sadd('payment_online_ds', self.qr_id)
                        for channel in self.qr_channels:
                            self.logger.info(f"Removing qr_id from payment_active_{channel}")
                            await self.redis.lrem(f'payment_active_{channel}', 0, self.qr_id)
                            self.logger.info(f"Adding qr_id to payment_active_{channel}")
                            await self.redis.rpush(f'payment_active_{channel}', self.qr_id)
                            self.logger.info(f"【码监控】: 准备将码 {self.qr_id} 重新添加到 Redis 队列 'payment_active_{channel}' 的队尾。")
                elif _type == 'df':
                    sql = """select * from orders_df where payment_id=%s and status in (1,2)"""
                    order = await self.query(sql, self.qr_id)
                    if order:
                        return dict(code=201, msg='On Fail.Old order not success',
                                    data=json.dumps({'status': 0, 'type': _type}))
                    if _is_easypaisa_payment(bank):
                        df_enabled = _as_int(bank.get('payout_status')) == 1
                        self.logger.info(
                            "EasyPaisa monitor Online(df) 已退役为只读: payment_id=%s payout_status=%s",
                            self.qr_id,
                            bank.get('payout_status'),
                        )
                        if not df_enabled:
                            return dict(code=201, msg='On Fail.', data=json.dumps({'status': 0, 'type': _type}))
                    else:
                        await self.redis.sadd('payment_online_df', self.qr_id)
                        await self.redis.lrem('payment_active_df', 0, self.qr_id)
                        await self.redis.rpush('payment_active_df', self.qr_id)
                return dict(code=201, msg='On Success.', data=json.dumps({'status': 1, 'type': _type}))
            return dict(code=201, msg='On Fail.', data=json.dumps({'status': 0, 'type': _type}))
        else:
            if not _type or _type == 'ds':
                # 下线需先读 bank_type 再分流
                bank = await self.get_result_by_condition(
                    'payment', ['bank_type', 'bank_type_id', 'channel'], {'id': self.qr_id}
                )
                if _is_easypaisa_payment(bank):
                    self.logger.info(
                        "EasyPaisa monitor Offline(ds) 已退役为 no-op: payment_id=%s",
                        self.qr_id,
                    )
                else:
                    # 非 EP 通道：保留原 legacy 写入
                    await self.redis.srem('payment_online_ds', self.qr_id)
                    # 下线删除所有通道
                    pattern_t = 'payment_active_*'
                    _active_channel = await self.redis.keys(pattern=pattern_t)
                    self.logger.info(f"Active channels for offline removal: {_active_channel}")
                    for i in _active_channel:
                        self.logger.info(f"Removing qr_id from {i}")
                        await self.redis.lrem(i, 0, self.qr_id)
            if not _type or _type == 'df':
                bank = await self.get_result_by_condition(
                    'payment', ['bank_type', 'bank_type_id', 'channel'], {'id': self.qr_id}
                )
                if _is_easypaisa_payment(bank):
                    self.logger.info(
                        "EasyPaisa monitor Offline(df) 已退役为 no-op: payment_id=%s",
                        self.qr_id,
                    )
                else:
                    await self.redis.srem('payment_online_df', self.qr_id)
                    await self.redis.lrem('payment_active_df', 0, self.qr_id)
            if not _type:
                await self.redis.delete('qrcode_key_{id}'.format(id=self.qr_id))
            return dict(code=201, msg='Off success.', data=json.dumps({'status': 0, 'type': _type}))

    async def new_record(self, data):
        if await self.is_null(data, ['bank_name', 'amount', 'content', 'sign']):
            return dict(code=99, msg='Abnormal data')
        key = await self.redis.get('qrcode_key_{id}'.format(id=self.qr_id))
        data_sign = "bank_name={bank_name}&amount={amount}&content={content}&key={key}".format(
            bank_name=data['bank_name'], amount=data['amount'], content=data['content'], key=key)
        self.logger.info('监控调用:' + data_sign)

        # md5 = hashlib.md5()
        # md5.update(data_sign.encode(encoding='UTF-8'))
        # r = md5.hexdigest()
        # if not r == data['sign']:
        #     return dict(code=99, msg='Sign error')
        data['admin_id'] = self.current_user['id']
        data['payment_id'] = self.qr_id
        # 解析
        # 直接将 data['amount'] 转换为字符串
        data['amount'] = str(data['amount'])
        data['amount'] = data['amount'].replace(',', '')
        amount = Decimal(data['amount'])
        # 删除无用数据方便存入
        del data['sign']
        del data['type']
        try:
            analyze = await eval("bank_analysis." + data['bank_name'])(self, data['content'], amount)
            if await self.is_null(analyze, ['trade_type']):
                data['trade_type'] = 0
                del data['bank_name']
                data['partner_id'] = self.partner_id
                await self.create_result('bank_record', data)
                return dict(code=99, msg='Analysis Error')
        except Exception as e:
            data['trade_type'] = 0
            del data['bank_name']
            data['partner_id'] = self.partner_id
            await self.create_result('bank_record', data)
            return dict(code=99, msg='Analysis Error:{}'.format(e))
        else:
            data['callback'] = 0
            try:
                data = {**data, **analyze}
                r = dict()
                if data['trade_type'] == 1:
                    # 代收通过utr和金额查找重复订单
                    if await self.get_result_by_condition('bank_record', ['*'],
                                                          {'utr': data['utr'], 'amount': data['amount'],
                                                           'trade_type': 1}):
                        return dict(code=99, msg='Record already exists')
                    r = await callback.success_ds(self, data)
                elif data['trade_type'] == 2:
                    if await self.get_result_by_condition('bank_record', ['id'],{'utr': data['utr'], 'amount': data['amount'],'trade_type': 2, 'payment_id': data['payment_id']}):
                        return dict(code=99, msg='Record already exists')
                    r = await callback.success_df(self, data)
                elif data['trade_type'] == 3:
                    r = await callback.sxf_df(self, data)
                elif data['trade_type'] == 4:
                    r = await callback.cancel_df(self, data)
                # 代收回调失败额外扣除
                if r['code'] == 99 and data['trade_type'] == 1:
                    ew_code = await self.create_order_code('EW')  # 额外流水号
                    async with self.application.db.acquire() as conn:
                        async with conn.cursor(DictCursor) as cur:
                            if not await self.change_balance(conn, cur, 'partner', self.partner_id,
                                                             -Decimal(data['amount']), ew_code, 0):
                                self.logger.warning('utr:{}Failed to deduct partner balance'.format(data['utr']))
                                await conn.rollback()
                            else:
                                data['ew_code'] = ew_code
                                data['if_ew'] = '1'
                                await conn.commit()
                if r['code'] == 100:
                    data['callback'] = 1
                    data['order_code'] = r['order']
                del data['bank_name']
                data['partner_id'] = self.partner_id
                await self.create_result('bank_record', data)
                return r
            except Exception as e:
                del data['bank_name']
                data['partner_id'] = self.partner_id
                await self.create_result('bank_record', data)
                return dict(code=99, msg='Callback Error:{}'.format(e))

    # 回退订单
    async def cancel_order(self, code):
        # condition = {'code': code, 'payment_id': self.qr_id, 'status': 1}
        # order = await self.get_result_by_condition('orders_df', ['amount'], condition)
        # if not order:
        #     return {'code': 99, 'data': None, 'message': 'cancel fail. no order'}
        # update_data = {'status': 0, 'partner_id': None, 'payment_id': None}
        # if not await self.update_result('orders_df', update_data, condition):
        #     return {'code': 99, 'data': None, 'message': 'cancel fail.'}
        # # 重新派单 接单
        # await self.redis.publish('order_df_push', '{code}_{amount}'.format(code=code, amount=order['amount']))
        # if await self.redis.sismember('payment_online_df', self.qr_id):
        #     await self.redis.lrem('payment_active_df', 0, self.qr_id)
        #     await self.redis.rpush('payment_active_df', self.qr_id)
        return {'code': 204, 'data': None, 'message': 'return order success.'}
