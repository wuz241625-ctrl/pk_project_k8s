import decimal
import json
from datetime import datetime
from decimal import Decimal

import tornado
from aiomysql import DictCursor

from application.base import BaseHandler

# 获取系统收款信息
from application.message import msg


# class getSystemCard(BaseHandler):
#     async def post(self):
#         data = await self.get_results_by_condition('sys_payment', ['id', 'account', 'name', 'type'], {'status': 1})
#         result = dict(code=20000, data=data, msg='获取成功')
#         return await self.json_response(result)


# 获取码商Usdt充值订单
class getUsdtRecharge(BaseHandler):

    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)

        condition, time_create_between = await self.split_between_condition(data['serchData'], 'created_at')
        condition, time_success_between = await self.split_between_condition(condition, 'paid_at')
        between = None
        if time_create_between:
            between = time_create_between
        if not between:
            between = time_success_between

        if not condition or not condition['serial_number'] and not between:
            between = {'key': 'created_at', 'start': datetime.today().date(), 'end': datetime.now()}
        # 获取顶级id下的所有订单
        top_partner_sql_part = ''
        partner_ids = []
        if 'top_partner_id' in condition.keys():
            partner_ids = await self.get_partners(condition['top_partner_id'])
            del condition['top_partner_id']
            if partner_ids:
                _partner_ids = ','.join(['%s'] * len(partner_ids))
                top_partner_sql_part = ' user_id in ({partner_ids})'.format(partner_ids=_partner_ids)
        sql_part = ''
        values = []
        if condition:
            for k in list(condition.keys()):
                if not condition[k] and condition[k] != 0:
                    condition.pop(k)
        if condition or between:
            sql_part += ' where '
        if condition:
            where_key, where_val = await self.dict_to_and(condition)
            sql_part += ' {keys} '.format(keys=where_key)
            values += where_val
        if between:
            bt_key, bt_start, bt_end = await self.dict_to_between(between)
            if condition:
                sql_part += " and " + bt_key
            else:
                sql_part += bt_key
            values += [bt_start, bt_end]

        if sql_part == '':
            if top_partner_sql_part:
                sql_part = ' where ' + top_partner_sql_part
                values = partner_ids
        else:
            if top_partner_sql_part:
                sql_part += ' and ' + top_partner_sql_part
                values.extend(partner_ids)

        # 如果是推广账号，则过滤出推广账号下的码商订单
        if str(self.current_user['role_id']) == '19':
            tg_partners_ids = await self.get_partners_by_parent_id(self.current_user['parent_id'])
            if sql_part == '':
                sql_part = ' where user_id in ({})'.format(tg_partners_ids)
            else:
                sql_part += ' and user_id in ({})'.format(tg_partners_ids)

        # 获取所有数据总数
        sql = "select count(id) from usdt_deposit_orders"
        sql += sql_part
        total = await self.query(sql, *values)
        if total:
            total = total[0]['count(id)']
        else:
            total = 0
        # 获取所有数据的指定key数据
        keys_count = ['total_amount', 'status']
        sql = "select {keys} from usdt_deposit_orders ".format(keys=await self.list_keys(keys_count))
        sql += sql_part
        count = await self.query(sql, *values)
        # 获取分页数据
        sql = "select * from {table}  where id in (select id from {table} ".format(table='usdt_deposit_orders')
        order_by = ') order by id desc '
        sql += sql_part + order_by
        if data['size'] and data['page'] > -1:
            sql += 'limit %s offset %s'
            values += [data['size'], (data['page'] - 1) * data['size']]
        data_r = await self.query(sql, *values)

        # data_r, total, count = await self.get_result('usdt_deposit_orders', ['*'], keys_count, condition, between, data['size'], data['page'])
        count_r = {'failOrder': 0, 'successOrder': 0, 'processing': 0, 'amount': decimal.Decimal(0), 'processing_amount': decimal.Decimal(0)}
        for i in count:
            if i['status'] == 2:
                count_r['successOrder'] += 1
                count_r['amount'] += Decimal(i['total_amount'])
            elif i['status'] == -1:
                count_r['failOrder'] += 1
            else:
                count_r['processing'] += 1
                count_r['processing_amount'] += Decimal(i['total_amount'])
        result = dict(code=20000, data=data_r, total=total, count=count_r, msg='获取成功')
        return await self.json_response(result)

# 处理码商Usdt充值订单
class handleUsdtRechargePartner(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['status', 'serial_number']):
            return await self.json_response(data=msg[10007])
        code = data['serial_number']
        txid = data['txid']
        del data['serial_number']
        del data['txid']

        # 获取锁，10秒内锁定
        code_lock_key = "grab_usdt_" + code
        code_lock = await self.redis.setnx(code_lock_key, 1)
        if not code_lock:
            return await self.json_response(msg[10032])
        await self.redis.expire(code_lock_key, 10)

        order = await self.get_result_by_condition('usdt_deposit_orders', ['serial_number', 'total_amount', 'status', 'user_id'], {'serial_number': code})
        if not order:
            return await self.json_response(msg[10036], code_lock_key)

        # 驳回
        if data['status'] == -1:
            if not order['status'] in [1]:
                return await self.json_response(msg[10032], code_lock_key)
            if not await self.update_result('usdt_deposit_orders', {'status': -1,'admin_id': self.current_user['id']}, {'serial_number': code}):
                return await self.json_response(msg[10007], code_lock_key)
            self.logger.warning('码商usdt充值订单，驳回成功={code}, 操作人{admin}'.format(code=code, admin=self.current_user['id']))
        # 确认
        if data['status'] == 2:
            # --- 查询订单的 SQL 语句 ---
            sql_select_order = """
                SELECT serial_number, total_amount, status, user_id
                FROM usdt_deposit_orders
                WHERE txid = %s AND serial_number != %s
                LIMIT 1
            """
            
            if not order['status'] in [-1,1]:
                return await self.json_response(msg[10032], code_lock_key)
            async with self.application.db.acquire() as conn:
                async with conn.cursor(DictCursor) as cur:
                    try:
                        # 执行查询
                        await cur.execute(sql_select_order, (txid, code))
                        
                        # 获取查询结果
                        result = await cur.fetchone()  # 使用 fetchone() 获取第一行结果
                        
                        if result:
                            order_number = result.get('serial_number')
                            formatted_txid = f"{txid[:4]}****{txid[-4:]}"
                            error_message = f"该交易ID ({formatted_txid}) 已在订单 {order_number} 中回调。"
                            self.logger.warning(error_message)
                            # 释放锁并返回错误
                            await self.redis.delete(code_lock_key)
                            # 将动态值直接放在响应数据中
                            response_data = {
                                'code': 60350,
                                'message': error_message
                            }
                            
                            return await self.json_response(response_data)
                    
                        if not await self.change_balance(conn, cur, 'partner', order['user_id'], order['total_amount'], code, 7):
                            self.logger.warning('确认异常={code}, 余额变动错误'.format(code=code))
                            await conn.rollback()
                            return await self.json_response(msg[10007], code_lock_key)
                        if not await self.update_result('usdt_deposit_orders', {'status': 2, 'paid_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),'admin_id': self.current_user['id']}, {'serial_number': code}):
                            self.logger.warning('确认异常={code}, 更新订单出错'.format(code=code))
                            await conn.rollback()
                            return await self.json_response(msg[10007], code_lock_key)

                        # 仅外部码商才能参与代付优惠
                        partner_id = order['user_id']
                        amount = order['total_amount']
                        partner = await self.get_result_by_condition('partner', ['id', 'type'], {'id': partner_id})
                        if partner and partner.get('type') == 1:
                            # 代付优惠
                            disprice = Decimal(0)
                            range_df = (await self.get_cache_result('sys_info', ['range_usdt_df']))['range_usdt_df']
                            if range_df:
                                range_df = json.loads(range_df)
                                for i in range(1, 7):
                                    if range_df['isOpen' + str(i)] == 1:
                                        if Decimal(range_df['rangemin' + str(i)]) <= amount <= Decimal(
                                                range_df['rangemax' + str(i)]):
                                            disprice = Decimal(range_df['disprice' + str(i)])
                                            self.logger.info(
                                                '代付优惠 disprice:{disprice} rangemin:{rangemin} rangemax:{rangemax} amount:{amount} '.format(
                                                    disprice=disprice, rangemin=range_df['rangemin' + str(i)],
                                                    rangemax=range_df['rangemax' + str(i)], amount=amount))
                                            break
                            # 代付优惠入库
                            if disprice > 0:
                                if not await self.change_balance(conn, cur, 'partner', partner_id, disprice, code,
                                                                 10):
                                    await conn.rollback()
                                    return dict(code=99, msg='Failed to add partner balance')
                            
                            # 2. 更新usdt_deposit_orders的txid
                            update_txid_sql = """
                                UPDATE usdt_deposit_orders
                                SET txid = %s
                                WHERE serial_number = %s LIMIT 1
                            """
                            
                            # 执行更新txid操作
                            await cur.execute(update_txid_sql, (txid, code))
                
                    except Exception as e:
                        self.logger.warning('确认异常={code},非法数据={e}'.format(code=code, e=e))
                        await conn.rollback()
                        return await self.json_response(msg[10007], code_lock_key)
                    else:
                        await conn.commit()
                        self.logger.warning('码商usdt充值订单，确认成功={code}, 操作人{admin}'.format(code=code, admin=self.current_user['id']))
        result = dict(code=20000, msg='成功')
        return await self.json_response(result, code_lock_key)