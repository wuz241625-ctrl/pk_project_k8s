import decimal
import json
from decimal import Decimal

import tornado

from application.base import BaseHandler
from application.message import msg


# 获取
class getOther(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data_r = await self.get_result_no_condition('sys_info', ['bulletin', 'telegram', 'rate_df', 'status_df', 'expired_status_df', 'usdt_exchange_rate','usdt_exchange_status','usdt_exchange_bonus_rate','usdt_amount_limit','merchant_ids'])
        gonghu_ds_payment = await self.redis.get('gonghu_ds_payment')
        data_r['gonghu_ds_payment'] = gonghu_ds_payment
        payment_ids = await self.redis.get('send_orders_ds_false_limit')
        data_r['payment_ids'] = payment_ids
        unlock_amount = await self.redis.get('unlock_amount')
        data_r['unlock_amount'] = unlock_amount
        result = dict(code=20000, data=data_r, msg='获取成功')
        return await self.json_response(result)

class getWeight(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data_r = await self.get_results_no_condition('payment_weight', ['id,value,weight,payment_numbers,type,time_updated'])
        result = dict(code=20000, data=data_r, msg='获取成功')
        return await self.json_response(result)

class updateWeight(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['data', 'google']):
            return await self.json_response(msg[10005])
        # 验证谷歌密钥
        r = await self.get_result_by_condition('admin', ['ggkey'], {"id": self.current_user['id']})
        if not await self.check_googl_code(data['google'], r['ggkey']):
            return await self.json_response(data=msg[10003])
        for i in data['data']:
            sql = "update payment_weight set weight=%s, time_updated=NOW() where id=%s"
            if not await self.execute(sql, i['weight'], i['id']):
                self.logger.error(str(self.current_user['id']) + ' 写入payment_weight记录异常' + json.dumps(i))
        result = dict(code=20000, msg='更新成功')
        return await self.json_response(result)

# 更新
class updateOther(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        try:
            # --- 日志：记录请求开始 ---
            self.logger.info("开始处理 updateOther 请求.")
            
            data = json.loads(self.request.body)
            # --- 日志：记录接收到的原始数据 ---
            self.logger.info(f"接收到请求数据: {json.dumps(data, ensure_ascii=False)}")

            # --- 验证：必填字段检查 ---
            if await self.is_null(data, ['rate_df', 'bulletin', 'telegram', 'google', 'status_df', 'usdt_exchange_rate', 'usdt_exchange_status', 'usdt_exchange_bonus_rate', 'usdt_amount_limit', 'merchant_ids']):
                # --- 日志：记录必填字段校验失败 ---
                self.logger.warning(f"数据校验失败：必填字段缺失或为空。当前数据Keys: {list(data.keys())}")
                return await self.json_response(msg[10005])

            # --- 验证：rate_df 范围检查 ---
            if Decimal(data['rate_df']) >= Decimal(1):
                # --- 日志：记录 rate_df 验证失败 ---
                self.logger.warning(f"rate_df 验证失败：值 '{data['rate_df']}' 不符合要求 (>= 1)")
                return await self.json_response(msg[10005])

            # --- 验证：status_df 值检查 ---
            if data['status_df'] not in [0, 1]:
                # --- 日志：记录 status_df 验证失败 ---
                self.logger.warning(f"status_df 验证失败：值 '{data['status_df']}' 不在 [0, 1] 范围内")
                return await self.json_response(msg[10005])

            # --- 验证：谷歌密钥 ---
            r = await self.get_result_by_condition('admin', ['ggkey'], {"id": self.current_user['id']})
            self.logger.info(f"查询到用户 {self.current_user['id']} 的谷歌密钥.")
            if not r or not await self.check_googl_code(data['google'], r['ggkey']):
                # --- 日志：记录谷歌验证码校验失败 ---
                self.logger.warning(f"谷歌验证码校验失败。输入值: '{data['google']}'")
                return await self.json_response(data=msg[10003])

            # --- 验证：usdt_exchange_rate 范围检查 ---
            if "usdt_exchange_rate" in data.keys() and data['usdt_exchange_rate']:
                if Decimal(data['usdt_exchange_rate']) <= Decimal(0):
                    # --- 日志：记录 usdt_exchange_rate 验证失败 ---
                    self.logger.warning(f"usdt_exchange_rate 验证失败：值 '{data['usdt_exchange_rate']}' 不符合要求 (<= 0)")
                    return await self.json_response(msg[10005])

            # --- 验证：usdt_exchange_bonus_rate 范围检查 ---
            if "usdt_exchange_bonus_rate" in data.keys() and data['usdt_exchange_bonus_rate']:
                rate = Decimal(data['usdt_exchange_bonus_rate'])
                if rate < Decimal(0) or rate >= Decimal(1): # 修改逻辑以符合 <0 或 >=1
                    # --- 日志：记录 usdt_exchange_bonus_rate 验证失败 ---
                    self.logger.warning(f"usdt_exchange_bonus_rate 验证失败：值 '{rate}' 不在 [0, 1) 范围内")
                    return await self.json_response(msg[10005])

            # --- 处理：gonghu_ds_payment ---
            redis_gonghu_ds_payment = await self.redis.get('gonghu_ds_payment')
            gonghu_ds_payment = None
            if "gonghu_ds_payment" in data.keys() and data['gonghu_ds_payment']:
                original_value = data["gonghu_ds_payment"]
                data["gonghu_ds_payment"] = original_value.replace('，', ',')
                gonghu_ds_payment = []
                for i in data["gonghu_ds_payment"].split(','):
                    if i:
                        gonghu_ds_payment.append(i.strip())
                if redis_gonghu_ds_payment == original_value.replace('，', ','): # 使用原始值进行比较
                    gonghu_ds_payment = None
                
                # --- 日志：记录 gonghu_ds_payment 处理结果 ---
                if gonghu_ds_payment is not None:
                    self.logger.info(f"gonghu_ds_payment 已处理。旧值: '{redis_gonghu_ds_payment}', 新值: '{','.join(gonghu_ds_payment)}'")
                    await self.redis.set('gonghu_ds_payment', ','.join(gonghu_ds_payment))
                else:
                    self.logger.info("gonghu_ds_payment 值未改变，跳过更新。")

            del data['gonghu_ds_payment']

            # --- 处理：merchant_ids ---
            if "merchant_ids" in data.keys() and data['merchant_ids']:
                try:
                    original_merchants = data["merchant_ids"]
                    data["merchant_ids"] = original_merchants.replace('，', ',')
                    usdt_amount_limit = []
                    
                    # --- 日志：记录 merchant_ids 验证开始 ---
                    self.logger.info(f"开始验证 merchant_ids. 原始值: '{original_merchants}', 处理后: '{data['merchant_ids']}'")

                    for merchant_id in data["merchant_ids"].split(','):
                        merchant_id = merchant_id.strip()
                        if merchant_id:
                            r = await self.get_result_by_condition('merchant', ['id'], {"id": merchant_id})
                            if not r:
                                # --- 日志：记录商户号不存在 ---
                                self.logger.warning(f"商户号 {merchant_id} 不存在。")
                                return await self.json_response(msg[10005])
                            usdt_amount_limit.append(merchant_id)
                    
                    data["merchant_ids"] = ','.join(usdt_amount_limit)
                    # --- 日志：记录 merchant_ids 验证成功后的最终值 ---
                    self.logger.info(f"merchant_ids 验证成功。最终值: '{data['merchant_ids']}'")

                except Exception as e:
                    # --- 日志：捕获并记录处理 merchant_ids 的异常 ---
                    self.logger.error(f"处理 merchant_ids 时发生异常: {str(e)}", exc_info=True)
                    return await self.json_response(msg[10007])

            # --- 处理：payment_ids ---
            redis_payment_ids = await self.redis.get('payment_ids')
            payment_ids = None
            if "payment_ids" in data.keys() and data['payment_ids']:
                original_value = data["payment_ids"]
                data["payment_ids"] = original_value.replace('，', ',')
                payment_ids = []
                for i in data["payment_ids"].split(','):
                    if i:
                        payment_ids.append(i.strip())
                if redis_payment_ids == original_value.replace('，', ','):
                    payment_ids = None
                
                # --- 日志：记录 payment_ids 处理结果 ---
                if payment_ids is not None:
                    self.logger.info(f"payment_ids 已处理。旧值: '{redis_payment_ids}', 新值: '{','.join(payment_ids)}'")
                    await self.redis.set('send_orders_ds_false_limit', ','.join(payment_ids))
                else:
                    self.logger.info("payment_ids 值未改变，跳过更新。")
            del data['payment_ids']

            # --- 处理：unlock_amount ---
            redis_unlock_amount = await self.redis.get('unlock_amount')
            unlock_amount = None
            if "unlock_amount" in data.keys() and data['unlock_amount']:
                original_value = data["unlock_amount"]
                data["unlock_amount"] = original_value.replace('，', ',')
                unlock_amount = []
                for i in data["unlock_amount"].split(','):
                    if i:
                        unlock_amount.append(i.strip())
                if redis_unlock_amount == original_value.replace('，', ','):
                    unlock_amount = None
                
                # --- 日志：记录 unlock_amount 处理结果 ---
                if unlock_amount is not None:
                    self.logger.info(f"unlock_amount 已处理。旧值: '{redis_unlock_amount}', 新值: '{','.join(unlock_amount)}'")
                    await self.redis.set('unlock_amount', ','.join(unlock_amount))
                else:
                    self.logger.info("unlock_amount 值未改变，跳过更新。")
            del data['unlock_amount']

            del data['google']
            
            # --- 日志：准备更新数据库 ---
            self.logger.info(f"准备更新 sys_info 表。最终数据: {json.dumps(data, ensure_ascii=False)}")
            
            # --- 数据库更新操作 ---
            update_success = await self.update_result('sys_info', data, {'id': 1})
            
            # --- 日志：记录数据库更新结果 ---
            self.logger.info(f"数据库更新结果: {update_success}")
            if not update_success:
                # 检查 gonghu_ds_payment 是否为空，因为该值可能在 del 之前被移除
                if 'gonghu_ds_payment' not in data and gonghu_ds_payment is None:
                    self.logger.error("数据库更新失败，且没有其他 Redis 更新操作来保证成功。")
                return await self.json_response(msg[10007])

            # --- 缓存操作：延迟双删 ---
            self.logger.info("开始延迟双删 sys_info 缓存...")
            await self.delete_cache_result('sys_info', {'id': 1})
            
            # --- 成功返回 ---
            self.logger.info("sys_info 更新成功。")
            result = dict(code=20000, msg='更新成功')
            return await self.json_response(result)

        except json.JSONDecodeError:
            self.logger.error("请求体解析为 JSON 失败。")
            return await self.json_response(msg[10005])
        except Exception as e:
            # --- 日志：捕获并记录通用异常 ---
            self.logger.exception(f"处理 updateOther 请求时发生未捕获的异常: {str(e)}")
            return await self.json_response(msg[10007])
class getUsdtTransferAddress(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data_r = await self.get_cache_result('sys_info', ['id','usdt_received_address'])
        result = dict(code=20000, data=data_r, msg='获取成功')
        return await self.json_response(result)

class updateUsdtTransferAddress(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['id', 'google', 'usdt_received_address']):
            return await self.json_response(msg[10005])
        # 验证谷歌密钥
        r = await self.get_result_by_condition('admin', ['ggkey'], {"id": self.current_user['id']})
        if not await self.check_googl_code(data['google'], r['ggkey']):
            return await self.json_response(data=msg[10003])
        del data['google']
        del data['id']
        if not await self.update_result('sys_info', data, {'id': 1}):
            self.logger.error(str(self.current_user['id']) + ' 写入usdt_received_address记录异常' + json.dumps(data))
        # 延迟双删sys_info
        await self.delete_cache_result('sys_info', {'id': 1})
        result = dict(code=20000, msg='更新成功')
        return await self.json_response(result)


class MerchantPayLinks(BaseHandler):
    links_redis_key = 'merchant_pay_links'
    table_name = 'merchant_pay_links'

    async def update_redis_cache_links(self):
        links_data = await self.get_results_no_condition(self.table_name, "*")
        links = ','.join([link['pay_link'] for link in links_data])
        await self.redis.set(self.links_redis_key, links)

    @tornado.web.authenticated
    async def get(self):
        links_data = await self.get_results_no_condition(self.table_name, "*")
        result = dict(code=20000, data=links_data, msg='获取成功')
        return await self.json_response(result)

    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['pay_name', 'pay_link']):
            return await self.json_response(msg[10005])
        if not await self.create_result(self.table_name, data):
            return await self.json_response(msg[10004])

        await self.update_redis_cache_links()
        result = dict(code=20000, msg='添加成功')
        return await self.json_response(result)

    @tornado.web.authenticated
    async def put(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['id', 'pay_name', 'pay_link']):
            return await self.json_response(msg[10005])
        if not await self.update_result(self.table_name, data, {'id': data['id']}):
            return await self.json_response(msg[10005])
        await self.update_redis_cache_links()
        result = dict(code=20000, msg='修改成功')
        return await self.json_response(result)

    @tornado.web.authenticated
    async def delete(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['id']):
            return await self.json_response(msg[10005])
        if not await self.delete_result(self.table_name, {'id': data['id']}):
            return await self.json_response(msg[10006])
        await self.update_redis_cache_links()
        result = dict(code=20000, msg='删除成功')
        return await self.json_response(result)
