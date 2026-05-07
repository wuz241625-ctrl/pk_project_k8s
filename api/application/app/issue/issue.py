import datetime
import os.path
import time

from decimal import Decimal
from aiomysql import DictCursor

from application.base import BaseHandler
from application.message import msg
from application.payment_eligibility import can_dispatch_df


def _is_easypaisa_payment(payment):
    return (
        str((payment or {}).get('bank_type_id') or '') == '97'
        or str((payment or {}).get('bank_type') or '') == '97'
    )


async def Issue(self, action, data):
    if action == 'grabOrder':
        return await grabOrder(self, data)
    if action == 'getorderinfo':
        return await getOrder(self, data)
    if action == 'confirmUpload':
        return await confirmUpload(self, data)


# 抢单
async def grabOrder(self, data):
    if await self.is_null(data, ['code']):
        return msg[10100]
    partner = await self.get_result_by_condition('partner', ['certified', 'status', 'vip'], {'id': self.current_user['id']})
    if not partner['certified']:
        return msg[10400]
    # if not partner['status']:  # 锁定也可以抢单
    #     return msg[10401]

    order_info = await self.get_result_by_condition('orders_df', ['amount', 'status'], {'code': data['code']})
    if not order_info:
        self.logger.warning("代付抢单，无此订单{code}".format(code=data['code']))
        return msg[10403]
    if not order_info['status'] == 0:
        self.logger.warning("代付抢单，{code}状态不为派单中".format(code=data['code']))
        return msg[10403]

    data_update = dict(partner_id=self.current_user['id'], status=1)
    grab_key = 'grab_df_{}'.format(data['code'])
    if not await self.redis.setnx(grab_key, 1):
        return msg[10403]
    await self.redis.expire(grab_key, 3)
    # 订单限制
    if self.current_user['user_type'] == 0:
        # 内部码商
        if await self.is_null(data, ['payment_id']):
            return msg[10403]
        if not await self.get_result_by_condition('payment', ['*'], {'id': data['payment_id'], 'partner_id': self.current_user['id']}):
            return msg[10403]
        data_update['payment_id'] = data['payment_id']
    else:
        # 外部码商 payment_id也写进去
        if await self.is_null(data, ['payment_id']):
            return msg[10403]
        payment = await self.get_result_by_condition('payment', ['*'], {'id': data['payment_id'], 'partner_id': self.current_user['id']})
        if not payment:
            return msg[10403]
        if _is_easypaisa_payment(payment) and not can_dispatch_df(payment):
            self.logger.warning("代付抢单，{code},码商{partner} 监控代付{id}不在线".format(code=data['code'], partner=self.current_user['id'], id=data['payment_id']))
            return msg[10403]
        data_update['payment_id'] = data['payment_id']
        sql = """select * from orders_df where partner_id=%s and (status in (1,2) or (payment_img =0  and status>2 )) limit 1"""
        orders = await self.query(sql, self.current_user['id'])
        if orders:
            return msg[10402]
        # VIP规则 检测订单金额是否在可接范围内,并且余额是否足够
        partner_amount = await self.get_result_by_condition('vip', ['df_min', 'df_max'], {'vip': partner['vip']})
        if order_info['amount'] < partner_amount['df_min'] or order_info['amount'] > partner_amount['df_max']:
            self.logger.warning("代付抢单，{code},金额{amount},码商{partner} vip规则限制，vip等级{vip},最小{min},最大{max}".format(code=data['code'], amount=order_info['amount'], partner=self.current_user['id'], vip=partner['vip'], min=partner_amount['df_min'], max=partner_amount['df_max']))
            return msg[10403]
    data_update['time_accept'] = datetime.datetime.now()
    if not await self.update_result('orders_df', data_update, {'code': data['code'], 'status': 0}):
        return msg[10403]
    return msg[10404]


# 获取代付订单列表
async def getOrder(self, data):
    if await self.is_null(data, ['order_type', 'offset']):
        return msg[10100]
    order_type = data['order_type']
    if order_type == 0:
        keys = ['code', 'amount', 'earn_partner_self', 'time_create', 'payment_img']
        if 'code' in data:
            orders = await self.get_result_by_condition('orders_df', keys, {'code': data['code'], 'status': 0})
            if not orders:
                orders = []
            else:
                orders = [orders]
        else:
            orders = await self.get_result('orders_df', keys, {'status': 0}, data['offset'], order_by='asc')
    else:
        sql = """select code,status,amount,earn_partner_self,payment_account,payment_name,payment_bank,ifsc,payment_img, time_create from orders_df where partner_id=%s"""
        values = [self.current_user['id'], data['offset']]
        if order_type == 1:
            sql += ' and (status in (1,2) or (payment_img =0  and status>2 ))'
        elif order_type == 2:
            sql += ' and status in (3,4)'
        elif order_type == 3:
            sql += ' and status = -1'
        sql += ' order by id desc limit 5 offset %s'
        orders = await self.query(sql, *values)
    result = {'type': 'issue.getorderinfo', 'data': orders}
    return result


# 确认上传
async def confirmUpload(self, data):
    if await self.is_null(data, ['order_code']):
        return msg[10100]
    order_code = data['order_code']
    if not os.path.exists('static/upload/{}.jpg'.format(order_code)):
        return msg[10405]
    # update_data = {
    #     'status': 2,
    #     'payment_img': 1,
    #     'time_payed': datetime.datetime.now()
    # }
    # 使用锁，5s使用自旋锁, 防止取消的同时回调
    count_circle = 0
    while True:
        busy_key = 'grab_df_{code}'.format(code=order_code)
        if await self.redis.setnx(busy_key, 1):
            await self.redis.expire(busy_key, 10)
            break
        if count_circle >= 25:
            self.logger.warning('code:{}Do not operate frequently'.format(order_code))
            return dict(code=99, msg='Do not operate frequently')
        time.sleep(0.2)
        count_circle = count_circle + 1

    async with self.application.db.acquire() as conn:
        async with conn.cursor(DictCursor) as cur:
            try:
                # 查找订单
                sql_select_order = """select status from orders_df where code=%s"""
                if not await cur.execute(sql_select_order, order_code):
                    await conn.rollback()
                    self.logger.warning('上传凭证确认 ，订单未发现,code={code}'.format(code=order_code))
                    await self.redis.delete(busy_key)
                    return msg[10405]
                order = (await cur.fetchall())[0]
                if order['status'] == 1: # 未上传过
                    # 更新订单
                    sql_update_order = """update orders_df set payment_img=%s,time_payed=%s,status=%s where code=%s and status=1"""
                    if not await cur.execute(sql_update_order, (1, datetime.datetime.now(), 2, order_code)):
                        self.logger.warning('上传凭证确认 ，更新订单错误,code={code}'.format(code=order_code))
                        await self.redis.delete(busy_key)
                        await conn.rollback()
                        return msg[10405]
                if order['status'] > 1: # 上传过或订单已完成，还需要上传凭证
                    # 更新订单
                    sql_update_order = """update orders_df set payment_img=%s,time_payed=%s where code=%s"""
                    if not await cur.execute(sql_update_order, (1, datetime.datetime.now(), order_code)):
                        self.logger.warning('上传凭证确认 ，更新订单错误,code={code}'.format(code=order_code))
                        await self.redis.delete(busy_key)
                        await conn.rollback()
                        return msg[10405]
            except Exception as e:
                self.logger.warning('上传凭证确认 失败,code={code},异常={e}'.format(code=order_code, e=e))
                await conn.rollback()
                await self.redis.delete(busy_key)
                return msg[10405]
            else:
                await conn.commit()
                await self.redis.delete(busy_key)
                self.logger.info('上传凭证确认 成功,code={code}'.format(code=order_code))
    return msg[10406]


# 上传凭证
class upload(BaseHandler):
    async def post(self):
        try:
            token = self.request.arguments['token'][0]
            exp, user_id = await self.decode_token(token.decode('utf-8'))
            if datetime.datetime.now() > datetime.datetime.fromtimestamp(int(exp)):
                return await self.json_response(msg[10405])
            files = self.request.files
            arguments = self.request.arguments
            if not self.request.files or len(files) > 1 or not arguments:
                return await self.json_response(msg[10405])
            files = files['image'][0]
            if not files.filename.split('.')[1].lower() in ['jpg', 'jpeg', 'png', 'bmp', 'tif', 'tiff']:
                return await self.json_response(msg[10405])
            filename = arguments['code'][0].decode('utf-8')
            with open("static/upload/{}.jpg".format(filename), 'wb') as f:
                f.write(files['body'])
            return await self.json_response(msg[10406])
        except Exception as e:
            self.logger.exception(e)
            return await self.json_response(msg[10405])
