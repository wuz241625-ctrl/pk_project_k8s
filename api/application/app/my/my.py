import datetime
import json
import time

import bcrypt

from decimal import Decimal

from aiomysql import DictCursor

from application.message import msg
from application.payment_eligibility import can_dispatch_df, can_dispatch_ds


async def My(self, action, data):
    if action == 'getuserinfo':
        return await getuserinfo(self)
    if action == 'getorder':
        return await getorder(self, data)
    if action == 'getrecharge':
        return await getrecharge(self, data)
    if action == 'gettransfer':
        return await getTransfer(self, data)
    if action == 'transfer':
        return await transfer(self, data)
    if action == 'getrecord':
        return await getrecord(self, data)
    if action == 'getbanklist':
        return await getbanklist(self)
    if action == 'getbanklist2':
        return await getbanklist2(self)
    if action == 'getpayment':
        return await getpayment(self, data)
    if action == 'getOnlinePayment':
        return await getOnlinePayment(self, data)
    if action == 'addpayment':
        return await addpayment(self, data)
    if action == 'changepayment':
        return await change_payment(self, data)
    if action == 'delpayment':
        return await delete_payment(self, data)
    if action == 'sendCode':
        return await sendCode(self, data)
    if action == 'changepassword':
        return await change_password(self, data)
    if action == 'certified':
        return await certified(self, data)
    if action == 'otp':
        return await sendOTP(self, data)
    if action == 'editPayment':
        return await editPayment(self, data)


# 获取用户信息
async def getuserinfo(self):
    user_data = await self.get_result_by_condition('partner', ['id', 'name', 'balance', 'balance_frozen', 'balance_deposit', 'vip', 'cellphone', 'certified'], {'id': self.current_user['id']})
    user_data['balance_all'] = user_data['balance'] + user_data['balance_deposit'] + user_data['balance_frozen']
    sql = """select sum(amount) as balance_locking from orders_ds where partner_id=%s and status in (1,2)"""
    balance_locking = (await self.query(sql, self.current_user['id']))[0]['balance_locking']
    if balance_locking:
        user_data['balance_all'] += balance_locking
    user_data['vips'] = await self.get_results_no_condition('vip', ['vip', 'conditions'])
    result = {'type': 'my.getuserinfo', 'data': user_data}
    return result


# 提现表
async def getorder(self, data):
    if await self.is_null(data, ['offset']):
        return msg[10100]
    keys = ['code', 'amount', 'status', 'account', 'name', 'bank', 'ifsc', 'time_create']
    orders = await self.get_result('partner_withdraw', keys, {'partner_id': self.current_user['id']}, data['offset'])
    result = {'type': 'record.getorder', 'data': orders}
    return result


# 充值表
async def getrecharge(self, data):
    if await self.is_null(data, ['offset']):
        return msg[10100]
    keys = ['code', 'amount', 'status', 'partner_id', 'bank', 'ifsc', 'name', 'account', 'time_create']
    content = {'partner_id': self.current_user['id']}
    content['status'] = data['status']
    orders = await self.get_result('partner_recharge', keys, content, data['offset'])
    result = {'type': 'record.getrecharge', 'data': orders}
    return result

# 转账表
async def getTransfer(self, data):
    if await self.is_null(data, ['offset']):
        return msg[10100]
    keys = ['code', 'amount', 'status', 'partner_id', 'to_partner_id', 'time_create']
    content = {'partner_id': self.current_user['id']}
    content['status'] = data['status']
    orders = await self.get_result('transfer', keys, content, data['offset'])
    result = {'type': 'record.gettransfer', 'data': orders}
    return result

# 流水表
async def getrecord(self, data):
    if await self.is_null(data, ['offset']):
        return msg[10100]
    condition = {'user_type': 'partner', 'user_id': self.current_user['id']}
    if not data['record_type'] == '':
        condition['record_type'] = data['record_type']
    keys = ['code', 'change_before', 'amount', 'change_after', 'record_type', 'time_create']
    record = await self.get_result('balance_record', keys, condition, data['offset'])
    result = {'type': 'record.getrecord', 'data': record}
    return result


# 获取银行列表
async def getbanklist(self):
    return {'type': 'payment.getbanklist', 'data': await self.get_results_no_condition('bank_type', ['id', 'name'])}

# 获取银行列表2
async def getbanklist2(self):
    keys = ['type']
    data_r = await self.get_result_by_condition('partner', keys, {'id': self.current_user['id']})
    if not data_r:
        return msg[10100]
    if data_r['type'] == 0:
        return {'type': 'payment.getbanklist2', 'data': await self.get_results_no_condition('bank_type', ['id', 'name'])}
    return {'type': 'payment.getbanklist2', 'data': await self.get_results_by_condition('bank_type', ['id', 'name'], {'type': data_r['type']})}


def _is_easypaisa_bank_type(bank_type):
    return str(bank_type) == '97'


def _is_jazzcash_bank_type(bank_type):
    return str(bank_type) == '98'


def _is_easypaisa_payment(payment_row):
    return (
        _is_easypaisa_bank_type((payment_row or {}).get('bank_type_id'))
        or _is_easypaisa_bank_type((payment_row or {}).get('bank_type'))
    )


def _is_mysql_final_state_payment(payment_row):
    return (
        _is_easypaisa_bank_type((payment_row or {}).get('bank_type_id'))
        or _is_easypaisa_bank_type((payment_row or {}).get('bank_type'))
        or _is_jazzcash_bank_type((payment_row or {}).get('bank_type_id'))
        or _is_jazzcash_bank_type((payment_row or {}).get('bank_type'))
    )


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def payment_business_status_from_config(wallet_status, status, certified, manual_status):
    business_enabled = (
        _as_int(wallet_status) == 1
        and _as_int(status) == 1
        and _as_int(certified) == 1
    )
    return {
        'collection_status': 1 if business_enabled and _as_int(manual_status) == 0 else 0,
        'payout_status': 1 if business_enabled else 0,
    }


def payment_update_for_status(payment_row, status):
    update_data = {'status': _as_int(status)}
    update_data.update(
        payment_business_status_from_config(
            payment_row.get('wallet_status'),
            update_data['status'],
            payment_row.get('certified'),
            payment_row.get('manual_status'),
        )
    )
    return update_data


def payment_update_for_certified(payment_row, certified):
    update_data = {'certified': _as_int(certified)}
    update_data.update(
        payment_business_status_from_config(
            payment_row.get('wallet_status'),
            payment_row.get('status'),
            update_data['certified'],
            payment_row.get('manual_status'),
        )
    )
    return update_data


async def _apply_payment_online_fields(self, payment_row):
    if _is_mysql_final_state_payment(payment_row):
        payment_row['online_ds'] = 1 if can_dispatch_ds(payment_row) else 0
        payment_row['online_df'] = 1 if can_dispatch_df(payment_row) else 0
        return

    payment_row['online_ds'] = 0
    payment_row['online_df'] = 0

# 获取收款信息
async def getpayment(self, data):
    if await self.is_null(data, ['offset']):
        return msg[10100]
    keys = [
        'id', 'bank_type', 'bank_type_id', 'net_id', 'upi', 'phone', 'name',
        'status', 'certified', 'manual_status', 'wallet_status',
        'collection_status', 'payout_status',
    ]
    data_r = await self.get_result('payment', keys, {'partner_id': self.current_user['id']}, data['offset'])
    for i in data_r:  # 展示在线
        await _apply_payment_online_fields(self, i)
    result = {'type': 'payment.getpayment', 'data': data_r}
    return result

# 获取收款信息
async def getOnlinePayment(self, data):
    keys = [
        'id', 'bank_type', 'bank_type_id', 'net_id', 'upi', 'phone', 'name',
        'status', 'certified', 'manual_status', 'wallet_status',
        'collection_status', 'payout_status',
    ]
    data_r = await self.get_results_by_condition('payment', keys, {'partner_id': self.current_user['id']})
    data = []
    for i in data_r:  # 展示在线
        await _apply_payment_online_fields(self, i)
        if i.get('online_ds') or i.get('online_df'):
            data.append(i)
    result = {'type': 'payment.getOnlinePayment', 'data': data}
    return result

# 添加银行卡
async def addpayment(self, data):
    if await self.is_null(data, ['bank_type']):
        return msg[10100]
    if 'upi' in data.keys() and await self.is_exits('payment', 'upi', data['upi']):
        return msg[10600]
    # if 'phone' in data.keys() and not len(data['phone']) == 10:
    #     return msg[10610]
    if 'phone' in data.keys() and await self.get_results_by_condition('payment', ['phone'], {'phone': data['phone'], 'bank_type' : data['bank_type']}):
        return msg[10600]
    data['partner_id'] = self.current_user['id']
    data['bank_type_id'] = data['bank_type']
    if not await self.create_result('payment', data):
        return msg[10602]
    return msg[10601]


# 启动禁用银行卡
async def change_payment(self, data):
    if await self.is_null(data, ['id', 'status']):
        return msg[10100]
    payment_id = data['id']
    payment = await self.get_result_by_condition(
        'payment',
        [
            'certified', 'manual_status', 'wallet_status', 'status',
            'bank_type', 'bank_type_id', 'phone', 'account_type',
            'partner_id', 'channel',
        ],
        {'id': payment_id},
    )
    if not payment:
        return msg[10100]
    if _is_mysql_final_state_payment(payment):
        update_data = payment_update_for_status(payment, data['status'])
        if not await self.update_result('payment', update_data, {'id': payment_id}):
            return msg[10604]
        return msg[10603]
    if not await self.update_result('payment', {'status': data['status']}, {'id': payment_id}):
        return msg[10604]
    return msg[10603]


# 删除银行卡
async def delete_payment(self, data):
    # 码商暂时不能删除卡
    return msg[10606]
    if await self.is_null(data, ['id']):
        return msg[10100]
    # 查看是否有单
    partner_id = self.current_user['id']
    payment = await self.get_result_by_condition('payment', ['*'], {'id': data['id'], 'partner_id': partner_id})
    busy_key = 'payment_busy_{payment_id}_*'.format(payment_id=data['id'])
    if await self.redis.exists(busy_key):
        return msg[10607]
    # 插入到备用表
    if not await self.create_result('payment_d', payment):
        return msg[10606]
    if not await self.delete_result('payment', {'id': data['id'], 'partner_id': partner_id}):
        return msg[10606]
    return msg[10605]


# 获取验证码
async def sendCode(self, data):
    if data['cellphone']:
        cellphone = data['cellphone']
    else:
        partner = await self.get_result_by_condition('partner', ['cellphone'], {'id': self.current_user['id']})
        cellphone = partner['cellphone']
    if not await self.send_code(cellphone):
        return msg[10103]
    return msg[10102]


# 修改密码
async def change_password(self, data):
    if await self.is_null(data, ['password_type', 'new_password']):
        return msg[10100]
    partner_id = self.current_user['id']
    # 验证密码或验证码
    partner = await self.get_result_by_condition('partner', ['hash_login', 'cellphone'], {'id': partner_id})
    if data['password_type'] == 1:  # 旧密码验证
        if not data['old_password'] or not bcrypt.checkpw(data['old_password'].encode('utf8'),
                                                          partner['hash_login'].encode('utf8')):
            return msg[10611]
    else:  # 验证码验证
        if not await self.redis.get('phonecode{cellphone}_{code}'.format(cellphone=partner['cellphone'],
                                                                         code=data['cellphone_code'])):
            return msg[10612]
    # 重置密码
    if len(data['new_password']) < 6 or len(data['new_password']) > 12:
        return msg[10613]
    hash_password = await self.password_create(data['new_password'])
    if data['password_type'] == 0:  # 更新交易密码
        if not await self.update_result('partner', {'hash_trade': hash_password}, {'id': partner_id}):
            return msg[10613]
    else:  # 更新登录密码
        if not await self.update_result('partner', {'hash_login': hash_password}, {'id': partner_id}):
            return msg[10613]
    return msg[10614]


# 认证
# async def certified(self, data):
#     if await self.is_null(data, ['cellphone', 'cellphone_code']):
#         return msg[10100]
#     if not await self.redis.get(
#             'phonecode{cellphone}_{code}'.format(cellphone=data['cellphone'], code=data['cellphone_code'])):
#         return msg[10612]
#     if not await self.update_result('partner', {'cellphone': data['cellphone'], 'certified': 1},
#                                     {'id': self.current_user['id'], 'certified': 0}):
#         return msg[10615]
#     return msg[10616]


# 是否接单
async def certified(self, data):
    if await self.is_null(data, ['certified', 'id']):
        return msg[10100]
    if not data['certified'] in [0, 1]:
        return msg[10100]
    payment = await self.get_result_by_condition(
        'payment',
        ['bank_type', 'bank_type_id', 'wallet_status', 'status', 'manual_status'],
        {'id': data['id']},
    )
    update_data = payment_update_for_certified(payment, data['certified'])
    if not await self.update_result('payment', update_data, {'id': data['id']}):
        return msg[10619]
    if data['certified']:
        return msg[10620]
    return msg[10621]



# 返回OTP
async def sendOTP(self, data):
    try:
        self.logger.info("{id} sendOTP 收到验证码 {otp}".format(id=str(data['payment_id']), otp=str(data['otp'])))
        query_result = await self.get_result_by_condition('payment', ['id'], {'id': data['payment_id']})
        if not query_result:
            self.logger.error(f"未找到 payment_id {data['payment_id']} 对应的 bank type")
            return msg[10622]
    except Exception as e:
        self.logger.warning("sendOTP 错误 e:{e} 不存在".format(e=str(e)))
        return msg[10618]
    return msg[10617]

# 码商可以修改码的密码
async def editPayment(self, data):
    dataUpdate = dict()
    if not 'id' in data.keys():
        return msg[10625]
    if not data['id']:
        return msg[10625]
    if not await self.get_results_by_condition('payment', ['id'], {'id': data['id']}):
        return msg[10622]
    if not 'net_pw' in data.keys():
        return msg[10626]
    if not data['net_pw']:
        return msg[10626]
    if not 'net_id' in data.keys():
        return msg[10627]
    if not data['net_id']:
        return msg[10627]
    dataUpdate['net_id'] = data['net_id']
    dataUpdate['net_pw'] = data['net_pw']
    if not await self.update_result('payment', dataUpdate, {'id': data['id']}):
        return msg[10624]
    return msg[10623]

# 转账
async def transfer(self, data):
    if await self.is_null(data, ['amount', 'to_partner_id', 'password_trade']):
        return msg[10100]
    amount = Decimal(data['amount'])
    partner = await self.get_result_by_condition('partner', ['hash_trade'], {'id': self.current_user['id'], 'status': 1})
    # 接受码商可以被禁用的码商
    to_partner = await self.get_result_by_condition('partner', ['hash_trade'], {'id': data['to_partner_id']})
    if not partner:
        self.logger.warning("余额转账，码商 {partner} 不存在".format(partner=self.current_user['id']))
        return msg[10334]
    if not to_partner:
        self.logger.warning("余额转账，接受码商 {partner} 不存在".format(partner=data['to_partner_id']))
        return msg[10334]
    # 验证交易密码
    if not bcrypt.checkpw(data['password_trade'].encode('utf8'), partner['hash_trade'].encode('utf8')):
        return msg[10330]
    # 不允许多次提交
    sql = """select * from transfer where partner_id=%s and status in (0,1) and time_create>date_sub(now(), interval 24 hour)"""
    orders = await self.query(sql, self.current_user['id'])
    if orders:
        self.logger.warning("余额转账，码商 {partner} , 当日多次提交".format(partner=self.current_user['id']))
        return msg[10334]
    code = await self.create_order_code('Z')
    remark = str(self.current_user['id']) + "码商操作，转账至" + str(data['to_partner_id'])
    data_new = dict(code=code, partner_id=self.current_user['id'], to_partner_id=data['to_partner_id'], amount=amount, remark=remark)
    # 先预扣码商资金
    async with self.application.db.acquire() as conn:
        async with conn.cursor(DictCursor) as cur:
            try:
                k, p, v = await self.dict_to_kv(data_new)
                sql = "insert into {table} ({keys}) values ({vals})".format(table='transfer', keys=k, vals=p)
                if not await cur.execute(sql, (*v,)):
                    await conn.rollback()
                    self.logger.warning('创建转账异常={code}'.format(code=code))
                    return await self.json_response(data=msg[10332])
                if not await self.change_balance(conn, cur, 'partner', data_new['partner_id'], -data_new['amount'], code, 8, "转账至：" + str(data['to_partner_id'])):
                    self.logger.warning('创建转账异常={code}, 余额变动错误'.format(code=code))
                    await conn.rollback()
                    return await self.json_response(msg[10332])
            except Exception as e:
                self.logger.warning('创建转账异常={code},非法数据={e}'.format(code=code, e=e))
                await conn.rollback()
                return await self.json_response(msg[10332])
            else:
                await conn.commit()
                self.logger.warning("余额转账={code}，码商 {partner} 转账至{to_partner} , 提交成功".format(code=code, partner=self.current_user['id'], to_partner=str(data['to_partner_id'])))
    return msg[10335]
