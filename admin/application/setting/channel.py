import hashlib
import json
import requests
import tornado

from application.base import BaseHandler
from application.message import msg
from application.setting.otherpay_option import build_otherpay_option
from aiomysql import DictCursor
from datetime import datetime

# 切换系统代收代付总开关状态
class switchPaymentServiceState(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = await self.get_results_by_condition('sys_info', ['status_payment_service'], {"1": "1"})
        if data[0]['status_payment_service'] == 1:
            await self.update_result('sys_info', {"status_payment_service": 0}, {"status_payment_service": 1})
        elif data[0]['status_payment_service'] == 0:
            await self.update_result('sys_info', {"status_payment_service": 1}, {"status_payment_service": 0})

        # 切换状态后刷新缓存
        await self.update_cache_result('sys_info', {'id': 1})

        result = dict(code=20000, msg='更新成功')
        return await self.json_response(result)

# 获取系统代收代付总开关状态
class getPaymentServiceState(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = await self.get_results_by_condition('sys_info', ['status_payment_service'], {"1": "1"})
        result = dict(code=20000, data=data[0]['status_payment_service'], msg='获取成功')
        return await self.json_response(result)


# 切换系统JZ代付单独控制开关状态
class switchJazzCashPayoutServiceState(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = await self.get_results_by_condition('sys_info', ['status_jazzcash_payout_service'], {"1": "1"})
        if data[0]['status_jazzcash_payout_service'] == 1:
            await self.update_result('sys_info', {"status_jazzcash_payout_service": 0}, {"status_payment_service": 1})
        elif data[0]['status_jazzcash_payout_service'] == 0:
            await self.update_result('sys_info', {"status_jazzcash_payout_service": 1}, {"status_jazzcash_payout_service": 0})

        # 切换状态后刷新缓存
        await self.update_cache_result('sys_info', {'id': 1})

        result = dict(code=20000, msg='更新成功')
        return await self.json_response(result)

# 获取系统JZ代付单独控制开关状态
class getJazzCashPayoutServiceState(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = await self.get_results_by_condition('sys_info', ['status_jazzcash_payout_service'], {"1": "1"})
        result = dict(code=20000, data=data[0]['status_jazzcash_payout_service'], msg='获取成功')
        return await self.json_response(result)

# 获取三方支付列表
class getOtherPay(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = await self.get_results_by_condition(
            'otherpay',
            ['id', 'name', 'merchant_id'],
            {'status': 1}
        )
        data = [build_otherpay_option(item) for item in data]
        result = dict(code=20000, data=data, msg='获取成功')
        return await self.json_response(result)


# 获取
class getChannel(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['size', 'page']):
            return await self.json_response(data=msg[10007])
        keys = ['id', 'code', 'name', 'rate', 'rates', 'amount_min', 'amount_max', 'amount_fixed', 'fixed',
                'status', 'decimal_callback_enabled', 'decimal_min', 'decimal_max', 'is_show_qr']
        data_r, total = await self.get_result('channel', keys, None, None, None, data['size'], data['page'])
        result = dict(code=20000, data=data_r, total=total, msg='获取成功')
        return await self.json_response(result)


# 更新
class updateChannel(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if 'status' not in data and await self.is_null(data, ['id', 'code', 'name', 'rate', 'rates', 'fixed']):
            return await self.json_response(msg[10005])
        # 如果包含小数点回调配置，进行验证
        if 'decimal_callback_enabled' in data and data['decimal_callback_enabled']:
            if 'decimal_min' in data and 'decimal_max' in data:
                decimal_min = float(data['decimal_min'])
                decimal_max = float(data['decimal_max'])
                if decimal_min >= decimal_max or decimal_min < -0.99 or decimal_max > 0.99:
                    return await self.json_response(msg[10310])
        if not await self.update_result('channel', data, {'id': data['id']}):
            return await self.json_response(msg[10005])
        result = dict(code=20000, msg='更新成功')
        return await self.json_response(result)


# 一键全切
class changeOtherPay(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        # 记录请求的参数
        self.logger.info(f"请求参数: {data}")
        if await self.is_null(data, ['code', 'otherpay']):
            return await self.json_response(msg[10007])
        if data['otherpay'] == 0:
            data['otherpay'] = None
        # 记录更新前的参数
        self.logger.info(f"更新操作: 代码 = {data['code']}, 其他支付 = {data['otherpay']}")
         # 执行更新操作
        async with self.application.db.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                # 构建 SQL 更新语句，假设我们要根据 code 来更新 otherpay 字段
                sql_update_bank_record = """
                UPDATE merchant_channel
                SET 
                    otherpay = %s,
                    is_force = CASE 
                                WHEN %s IS NULL THEN 0
                                ELSE 1
                                END
                WHERE code = %s
                """

                # 执行更新操作
                if not await cur.execute(sql_update_bank_record, (data['otherpay'], data['otherpay'], data['code'])):
                    # 如果执行失败，回滚并返回错误信息
                    await conn.rollback()
                    return await self.json_response(msg[10007])

                # 如果执行成功，提交事务
                await conn.commit()
        # 构建查询语句
        sql = f"""
        SELECT COUNT(*) 
        FROM merchant_channel 
        WHERE code = %s AND otherpay = %s
        """

        # 执行查询，获取受影响的行数
        updated_rows = await self.query(sql, data['code'], data['otherpay'])

        # 如果没有更新的行数，返回错误信息
        if updated_rows == 0:
            self.logger.warning(f"更新失败，代码 = {data['code']}, 其他支付 = {data['otherpay']}")
            return await self.json_response(msg[10007])

        # 记录更新成功的日志
        self.logger.info(f"更新成功，代码 = {data['code']}, 其他支付 = {data['otherpay']}，更新的记录数 = {updated_rows}")

        # 获取更新后的记录数据
        data_after_update = await self.get_results_by_condition('merchant_channel', ['merchant_id', 'otherpay'], {'code': data['code'], 'otherpay': data['otherpay']})
        self.logger.info(f"更新后的记录：{data_after_update}")

        result = dict(code=20000, msg='更新成功')
        return await self.json_response(result)


# 下单测试
class testOrder(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        try:
            self.logger.info(f"testOrder begin call")
            data = json.loads(self.request.body)
            keys = ['id', 'mc_key']
            merchant = await self.get_result_by_condition('merchant', keys, {'id': data['merchant_id']})
            order_id = await self.create_order_code('T')
            date_p = {'mer_id': merchant['id'], 'order_id': order_id, 'gateway': data['channel_code'],
                      'amount': data['amount'], 'callback': 'sys', 'notify': 'sys'}
            dataList = []
            for key in sorted(date_p):
                if date_p[key]:
                    dataList.append("%s=%s" % (key, date_p[key]))
            signdata = "&".join(dataList).strip() + "&key=" + merchant['mc_key'].strip()
            md5 = hashlib.md5()
            md5.update(signdata.encode(encoding='UTF-8'))
            sign = md5.hexdigest().upper()
            date_p['sign'] = sign
            date_p['player_ip'] = data.get('ip', '')  # 如果 data['ip'] 不存在，则默认为空字符串
            date_p['user_id'] = data.get('user_id', '')
            url = self.application.api_url + '/pay'
            self.logger.info(f"testOrder {url} {date_p}")
            r = requests.post(url, date_p, timeout=15, verify=False)
            self.logger.info(f"testOrder {url} {date_p} {r.text}")
            ret = json.loads(r.text)
            return await self.json_response(ret)
        except Exception as e:
            self.logger.info(f"异常 {e} ")
            return await self.json_response(data=msg[10009])


# 代收配置-获取
class getDSSettings(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['size', 'page']):
            return await self.json_response(data=msg[10007])
        keys = [
            'id', 
            'merchant_id',  # 商户ID
            '`key`',        # 密钥
            'key2',         # 可以放公钥
            'key3',         # 可以放私钥
            '`name`',       # 支付名称
            'pay_url',      # 网关
            'channel_code', # 网关号
            'notify_ip',    # 回调IP
            'query_url',    # 查询网关
            'forcible',     # 是否强转
            'status',     # 状态、是否正常 0禁用，1正常
            'updated',      # 更新时间 
            'created'       # 创建时间
        ]
        data_r, total = await self.get_result('otherpay', keys, None, None, None, data['size'], data['page'])
        result = dict(code=20000, data=data_r, total=total, msg='获取成功')
        return await self.json_response(result)

# 代收配置-新增
class addDSSettings(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['merchant_id', 'key', 'name', 'pay_url', 'channel_code', 'notify_ip', 'query_url', 'forcible', 'status']):
            return await self.json_response(data=msg[10004])
        if await self.is_exits('otherpay', 'name', data['name']):
            return await self.json_response(msg[10008])
        now = datetime.now()
        data['updated'] = now
        data['created'] = now
        data.pop('id') 
        key_tmp = data.pop('key')
        data['`key`'] = key_tmp
        name_tmp = data.pop('name')
        data['`name`'] = name_tmp
        if not await self.create_result('otherpay', data):
            return await self.json_response(msg[10004])
        result = dict(code=20000, msg='添加成功')
        return await self.json_response(result)

# 代收配置-删除
class delDSSettings(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['id']) or not await self.delete_result('otherpay', {'id': data['id']}):
            return await self.json_response(msg[10007])
        result = dict(code=20000, msg='删除成功')
        return await self.json_response(result)

# 代收配置-修改
class edtDSSettings(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['id', 'merchant_id', 'key', 'name', 'pay_url', 'channel_code', 'notify_ip', 'query_url', 'forcible', 'status']):
            return await self.json_response(data=msg[10005])
        dataInDB = await self.get_result_by_condition('otherpay', ['id'], {"id": data['id']})        
        if not dataInDB:
            return await self.json_response(msg[10007])
        now = datetime.now()
        data['updated'] = now
        data.pop('id') 
        data.pop('created')
        key_tmp = data.pop('key')
        data['`key`'] = key_tmp
        name_tmp = data.pop('name')
        data['`name`'] = name_tmp
        if not await self.update_result('otherpay', data, {'id': dataInDB['id']}):
            return await self.json_response(msg[10005])
        result = dict(code=20000, msg='更新成功')
        return await self.json_response(result)


# 代付配置-获取
class getDFSettings(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['size', 'page']):
            return await self.json_response(data=msg[10007])
        keys = [
            'id', 
            'mer_id',       # 商户ID
            'mer_key',      # 密钥
            'mer_key2',     # 可以放公钥
            'mer_key3',     # 可以放私钥
            'mer_key4',     # 可以放其他参数
            'pay_name',     # 支付名称
            'pay_name_zh',  # 支付名称（中文）
            'pay_url',      # 网关
            'channel_code', # 网关号
            'notify_ip',    # 回调IP
            'query_url',    # 查询网关
            'is_self',      # 自身是否供应链 默认0不是
            'is_xiaoshu',   # 是否带小数 默认0不带
            'status',     # 状态、是否正常 0禁用，1正常
        ]
        data_r, total = await self.get_result('third_pay_df', keys, None, None, None, data['size'], data['page'])
        result = dict(code=20000, data=data_r, total=total, msg='获取成功')
        return await self.json_response(result)

# 代付配置-新增
class addDFSettings(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['mer_id', 'mer_key', 'pay_name', 'pay_name_zh', 'pay_url', 'notify_ip', 'query_url', 'is_self', 'is_xiaoshu', 'status']):
            return await self.json_response(data=msg[10004])
        if await self.is_exits('third_pay_df', 'pay_name', data['pay_name']):
            return await self.json_response(msg[10008])        
        data.pop('id') 
        if not await self.create_result('third_pay_df', data):
            return await self.json_response(msg[10004])
        result = dict(code=20000, msg='添加成功')
        return await self.json_response(result)

# 代付配置-删除
class delDFSettings(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['id']) or not await self.delete_result('third_pay_df', {'id': data['id']}):
            return await self.json_response(msg[10007])
        result = dict(code=20000, msg='删除成功')
        return await self.json_response(result)

# 代付配置-修改
class edtDFSettings(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['id', 'mer_id', 'mer_key', 'pay_name', 'pay_name_zh', 'pay_url', 'notify_ip', 'query_url', 'is_self', 'is_xiaoshu', 'status']):
            return await self.json_response(data=msg[10005])
        dataInDB = await self.get_result_by_condition('third_pay_df', ['id'], {"id": data['id']})        
        if not dataInDB:
            return await self.json_response(msg[10007])
        data.pop('id')
        if not await self.update_result('third_pay_df', data, {'id': dataInDB['id']}):
            return await self.json_response(msg[10005])
        result = dict(code=20000, msg='更新成功')
        return await self.json_response(result)
