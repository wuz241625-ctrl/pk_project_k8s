import decimal
import json
from datetime import datetime, timedelta

import tornado
from aiomysql import DictCursor

from application.base import BaseHandler
from application.timezone import display_today_between

# 获取系统收款信息
from application.message import msg


# class getSystemCard(BaseHandler):
#     async def post(self):
#         data = await self.get_results_by_condition('sys_payment', ['id', 'account', 'name', 'type'], {'status': 1})
#         result = dict(code=20000, data=data, msg='获取成功')
#         return await self.json_response(result)


# 获取码商充值订单
class getRechargePartner(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)

        condition, time_create_between = await self.split_between_condition(data['serchData'], 'time_create')
        condition, time_success_between = await self.split_between_condition(condition, 'time_success')
        between = None
        if time_create_between:
            between = time_create_between
        if not between:
            between = time_success_between

        if not condition or not condition['code'] and not between:
            between = display_today_between('time_create')

        keys_count = ['amount', 'status']
        data_r, total, count = await self.get_result('partner_recharge', ['*'], keys_count, condition, between, data['size'], data['page'])
        count_r = {'failOrder': 0, 'successOrder': 0, 'processing': 0, 'amount': decimal.Decimal(0), 'processing_amount': decimal.Decimal(0)}
        for i in count:
            if i['status'] == 2:
                count_r['successOrder'] += 1
                count_r['amount'] += i['amount']
            elif i['status'] == -1:
                count_r['failOrder'] += 1
            else:
                count_r['processing'] += 1
                count_r['processing_amount'] += i['amount']
        result = dict(code=20000, data=data_r, total=total, count=count_r, msg='获取成功')
        return await self.json_response(result)

# 删除码商充值订单统计
class deleteStaticsReport(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['id']) or not await self.delete_result('partner_summary', {'id': data['id']}):
            return await self.json_response(msg[10005])
        # **步骤 2: 查询 sys_settings 里的 partner_statics**
        sql_select = "SELECT value FROM sys_settings WHERE name = 'partner_statics' LIMIT 1"
        result = await self.query(sql_select)

        delete_id = str(data['partner_id'])  # 确保 id 是字符串格式
        self.logger.info(f"准备删除 ID: {delete_id}")
        if result:
            value_str = result[0]['value']
            self.logger.info(f"原始 partner_statics value: {value_str}")

            # **解析逗号分隔字符串**
            ids_list = value_str.split(",")  # 转换成列表
            self.logger.info(f"解析后的 ID 列表: {ids_list}")

            # **删除指定 ID**
            ids_list = [i for i in ids_list if i != delete_id]
            self.logger.info(f"更新后的 ID 列表: {ids_list}")

            # **如果有剩余 ID，更新数据库**
            if ids_list:
                new_value = ",".join(ids_list)  # 重新拼接回字符串
                sql_update = "UPDATE sys_settings SET value = %s WHERE name = 'partner_statics' LIMIT 1"
                await self.execute(sql_update, (new_value,))
                self.logger.info(f"成功更新 partner_statics 的 value: {new_value}")
            else:
                sql_update = "UPDATE sys_settings SET value = null WHERE name = 'partner_statics' LIMIT 1"
                await self.execute(sql_update)

        result = dict(code=20000, msg='删除成功')
        return await self.json_response(result)

# 添加码商充值订单统计
class addStaticsReport(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        try:
            # 解析请求体
            data = json.loads(self.request.body)
            self.logger.info("从请求体中获取 id...")

            # 获取传入的 id，格式应为 "11,22,33,44"
            add_ids_str = data.get('id', '')  
            if not add_ids_str:
                self.logger.warning("未提供 id 参数，返回错误信息")
                return await self.json_response(msg[10005])

            # **第三步：循环验证每个 ID**
            add_ids_list = add_ids_str.split(",")
            for partner_id in add_ids_list:
                check_partner_query = "SELECT COUNT(*) AS count FROM partner WHERE id = %s"
                partner_result = await self.query(check_partner_query, (partner_id,))

                if not partner_result or partner_result[0]['count'] == 0:
                    # **partner_id 不存在，跳过**
                    self.logger.info(f"partner_id {partner_id} 在 partner 表中不存在")
                    return await self.json_response(msg[10004])

            # 执行 SQL 更新
            sql = """
                UPDATE sys_settings 
                SET value = %s 
                WHERE name = 'partner_statics' 
                LIMIT 1
            """

            await self.execute(sql, (add_ids_str,))
            self.logger.info(f"成功更新 sys_settings 的 value: {add_ids_str}")

            # 返回成功响应
            result = dict(code=20000, msg='更新成功')
            return await self.json_response(result)

        except Exception as e:
            self.logger.error(f"更新 sys_settings 失败: {e}")
            return await self.json_response({"code": 50000, "msg": "服务器内部错误"})

# 获取码商充值订单统计
class getStaticsReport(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        condition, between = await self.split_between_condition(data['serchData'], 'formatted_date')
        # 获取顶级id下的所有下级
        partner_ids = []
        values = []
        sql_part = ''
        if between:
            key = between.get('key')
            start = between.get('start')
            end = between.get('end')
            if key and start and end:
                if sql_part == '':
                    sql_part = " where {key} BETWEEN %s AND %s".format(key=key)  # 添加 'BETWEEN' 子句
                else:
                    sql_part += " and {key} BETWEEN %s AND %s".format(key=key)  # 追加 'AND' 和 'BETWEEN'
                # 这里的 values 是查询条件参数，你需要在实际调用数据库时传递
                values += [start, end]
        # 获取所有数据总数
        sql = "select count(id) from partner_summary "
        # self.current_user['role_id'] = 19
        # self.current_user['parent_id'] = 1
        # print('current id===', self.current_user['parent_id'])
        # 如果是推广账号，则过滤出推广账号下的码商订单
        if str(self.current_user['role_id']) == '19':
            tg_partners_ids = await self.get_partners_by_parent_id(self.current_user['parent_id'])
            if sql_part == '':
                sql_part = ' where partner_id in ({})'.format(tg_partners_ids)
            else:
                sql_part += ' and partner_id in ({})'.format(tg_partners_ids)

        # 获取顶级id下的所有订单
        top_partner_sql_part = ''
        partner_ids = []
        if 'id' in condition.keys() and condition['id']: 
            partner_ids = await self.get_partners(condition['id'])
            del condition['id']
            if partner_ids:
                _partner_ids = ','.join(['%s'] * len(partner_ids))
                top_partner_sql_part = ' partner_id in ({partner_ids})'.format(partner_ids=_partner_ids)
            else:
                top_partner_sql_part = ' partner_id IN (NULL)'

        if sql_part == '':
            if top_partner_sql_part:
                sql_part = ' where ' + top_partner_sql_part
                values = partner_ids
        else:
            if top_partner_sql_part:
                sql_part += ' and ' + top_partner_sql_part
                values.extend(partner_ids)
        # 执行查询
        sql += sql_part
        total = await self.query(sql, *values)
        if total:
            total = total[0]['count(id)']
        else:
            total = 0
        # 获取分页数据
        sql = "select * from {table}  where id in (select id from {table} ".format(table='partner_summary')
        order_by = ') order by {order_field} {sort} '.format(order_field=data['order_field'], sort=data['sort'])
        sql += sql_part + order_by
        if data['size'] and data['page'] > -1:
            sql += 'limit %s offset %s'
            values += [data['size'], (data['page'] - 1) * data['size']]
        data_r = await self.query(sql, *values)

        # 查询 sys_settings 表，获取 partner_statics
        sql = "SELECT value FROM sys_settings WHERE name = 'partner_statics' LIMIT 1"
        result = await self.query(sql)

        # 解析查询结果
        addIds = result[0]['value'] if result and 'value' in result[0] else ""
        # 返回数据
        result = dict(code=20000, data=data_r, total=total, msg='获取成功', addIds=addIds)
        return await self.json_response(result)


# 处理码商充值订单
class handleRechargePartner(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        code = data['code']
        del data['code']

        # 获取锁，10秒内锁定
        code_lock_key = "handleRechargePartner_" + code
        code_lock = await self.redis.setnx(code_lock_key, 1)
        if not code_lock:
            return await self.json_response(msg[10032])
        await self.redis.expire(code_lock_key, 10)

        order = await self.get_result_by_condition('partner_recharge', ['code', 'amount', 'status', 'partner_id'], {'code': code})
        if not order:
            return await self.json_response(msg[10036], code_lock_key)

        # 驳回
        if data['status'] == -1:
            if not order['status'] in [1]:
                return await self.json_response(msg[10032], code_lock_key)
            if not await self.update_result('partner_recharge', {'status': -1}, {'code': code}):
                return await self.json_response(msg[10007], code_lock_key)
            self.logger.warning('码商充值订单，驳回成功={code}, 操作人{admin}'.format(code=code, admin=self.current_user['id']))

        # 处理
        if data['status'] == 1:
            if not order['status'] in [0, 1]:
                return await self.json_response(msg[10032], code_lock_key)
            payment_info = await self.get_result_by_condition('sys_payment', ['*'], {'id': data['sys_payment_id']})
            if not payment_info:
                return await self.json_response(msg[10033], code_lock_key)
            data['ifsc'] = payment_info['ifsc']
            data['bank'] = payment_info['bank']
            data['account'] = payment_info['account']
            data['name'] = payment_info['name']

            data['admin_id'] = self.current_user['id']
            # 绑定卡
            if order['status'] == 0:
                if not await self.update_result('partner_recharge', data, {'code': code, 'status': 0}):
                    self.logger.warning('绑定异常={code}, 更新订单出错'.format(code=code))
                    return await self.json_response(msg[10007], code_lock_key)
                self.logger.warning('码商充值订单，绑定成功={code}, 操作人{admin}'.format(code=code, admin=self.current_user['id']))
            # 更换卡
            if order['status'] == 1:
                #暂时不允许更换卡
                return await self.json_response(msg[10032], code_lock_key)
                if not await self.update_result('partner_recharge', data, {'code': code, 'status': 1}):
                    self.logger.warning('更换绑定异常={code}, 更换卡更新订单出错'.format(code=code))
                    return await self.json_response(msg[10007], code_lock_key)
                self.logger.warning('码商充值订单，更换绑定成功={code}, 操作人{admin}'.format(code=code, admin=self.current_user['id']))
        # 确认
        if data['status'] == 2:
            if not order['status'] == 1:
                return await self.json_response(msg[10032], code_lock_key)
            async with self.application.db.acquire() as conn:
                async with conn.cursor(DictCursor) as cur:
                    try:
                        if not await self.change_balance(conn, cur, 'partner', order['partner_id'], order['amount'], code, 7):
                            self.logger.warning('确认异常={code}, 余额变动错误'.format(code=code))
                            await conn.rollback()
                            return await self.json_response(msg[10007], code_lock_key)
                        if not await self.update_result('partner_recharge', {'status': 2, 'time_success': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, {'code': code}):
                            self.logger.warning('确认异常={code}, 更新订单出错'.format(code=code))
                            await conn.rollback()
                            return await self.json_response(msg[10007], code_lock_key)
                    except Exception as e:
                        self.logger.warning('确认异常={code},非法数据={e}'.format(code=code, e=e))
                        await conn.rollback()
                        return await self.json_response(msg[10007], code_lock_key)
                    else:
                        await conn.commit()
                        self.logger.warning('码商充值订单，确认成功={code}, 操作人{admin}'.format(code=code, admin=self.current_user['id']))
        result = dict(code=20000, msg='成功')
        return await self.json_response(result, code_lock_key)

# # 获取商户充值订单
# class getRechargeMerchant(BaseHandler):
#     async def post(self):
#         data = json.loads(self.request.body)
#         condition, between = await self.split_between_condition(data['serchData'], 'time_accept')
#         condition, between = await self.split_between_condition(condition, 'time_create')
#         keys = ['id', 'code', 'merchant_id', 'admin_id', 'amount', 'status', 'payment_type', 'payment_codes',
#                 'account', 'name', 'type', 'time_create', 'time_success']
#         keys_count = ['amount', 'status']
#         data_r, total, count = await self.get_result('merchant_recharge', keys, keys_count, condition, between,
#                                                      data['size'], data['page'])
#         count_r = {'failOrder': 0, 'successOrder': 0, 'processing': 0, 'amount': decimal.Decimal(0)}
#         for i in count:
#             if i['status'] == 2:
#                 count_r['successOrder'] += 1
#                 count_r['amount'] += i['amount']
#             elif i['status'] == -1:
#                 count_r['failOrder'] += 1
#             else:
#                 count_r['processing'] += 1
#         result = dict(code=20000, data=data_r, total=total, count=count_r, msg='获取成功')
#         return await self.json_response(result)
#
#
# # 处理商户充值订单
# class handleRechargeMerchant(BaseHandler):
#     async def post(self):
#         data = json.loads(self.request.body)
#         code = data['code']
#         del data['code']
#         order = await self.get_result_by_condition('merchant_recharge', ['amount', 'status', 'merchant_id'],
#                                                    {'code': code})
#         # 驳回
#         if data['status'] == -1:
#             if not await self.update_result('merchant_recharge', {'status': -1}, {'code': code}):
#                 return await self.json_response(msg[10007])
#         # 处理
#         if data['status'] == 1:
#             if data['payment_type'] == 1:
#                 # 发起代收
#                 order_data = {'amount': order['amount'], 'order_id': order['code']}
#                 if not await self.order('ds', order_data):
#                     return await self.json_response(msg[10007])
#                 # 更新状态
#                 if not await self.update_result('merchant_recharge', {'status': 1}, {'code': code}):
#                     return await self.json_response(msg[10007])
#             else:
#                 data['admin_id'] = self.current_user['id']
#                 # 绑定卡
#                 if order['status'] == 0:
#                     if not await self.update_result('merchant_recharge', data, {'code': code, 'status': 0}):
#                         return await self.json_response(msg[10007])
#                 # 更换卡
#                 if order['status']:
#                     payment = {'account': data['account'], 'name': data['name'], 'type': data['type']}
#                     if not await self.update_result('merchant_recharge', payment, {'code': code, 'status': 1}):
#                         return await self.json_response(msg[10007])
#         # 确认
#         if data['status'] == 2:
#             async with self.application.db.acquire() as conn:
#                 async with conn.cursor(DictCursor) as cur:
#                     try:
#                         if not await self.change_amount(conn, cur, order['amount'], 'balance_df', 'merchant',
#                                                         order['merchant_id'], code, 1, 'merchant_id',
#                                                         'balance_record_df'):
#                             await conn.rollback()
#                             return await self.json_response(msg[10007])
#                         if not await self.update_result('merchant_recharge', {'status': 2}, {'code': code}):
#                             await conn.rollback()
#                             return await self.json_response(msg[10007])
#                     except Exception as e:
#                         self.logger.warning('驳回异常={code},非法数据={e}'.format(code=code, e=e))
#                         await conn.rollback()
#                         return await self.json_response(msg[10007])
#                     else:
#                         await conn.commit()
#         result = dict(code=20000, msg='成功')
#         return await self.json_response(result)


# 获取码商提现订单
class getWithdrawPartner(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        condition, time_create_between = await self.split_between_condition(data['serchData'], 'time_create')
        condition, time_success_between = await self.split_between_condition(condition, 'time_success')
        between = None
        if time_create_between:
            between = time_create_between
        if not between:
            between = time_success_between

        if (not condition or not condition['code']) and not between:
            between = display_today_between('time_create')
        keys_count = ['amount', 'status']
        data_r, total, count = await self.get_result('partner_withdraw', ['*'], keys_count, condition, between,
                                                     data['size'], data['page'])
        count_r = {'failOrder': 0, 'successOrder': 0, 'processing': 0, 'amount': decimal.Decimal(0), 'processing_amount': decimal.Decimal(0)}
        for i in count:
            if i['status'] == 2:
                count_r['successOrder'] += 1
                count_r['amount'] += i['amount']
            elif i['status'] == -1:
                count_r['failOrder'] += 1
            else:
                count_r['processing'] += 1
                count_r['processing_amount'] += i['amount']
        result = dict(code=20000, data=data_r, total=total, count=count_r, msg='获取成功')
        return await self.json_response(result)


# 处理码商提现订单
class handleWithdrawPartner(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['code', 'status']):
            return await self.json_response(msg[10005])
        order = await self.get_result_by_condition('partner_withdraw', ['admin_id', 'amount', 'status', 'partner_id', 'payment_codes'], {'code': data['code']})
        # 驳回
        if data['status'] == -1:
            async with self.application.db.acquire() as conn:
                async with conn.cursor(DictCursor) as cur:
                    try:
                        # 退回余额
                        # if not await self.change_balance(conn, cur, order['amount'], 'balance', 'partner',
                        #                                  order['partner_id'], data['code'], 2, 'partner_id',
                        #                                  'balance_record'):
                        if not await self.change_balance(conn, cur, "partner", order['partner_id'], order['amount'], data['code'], 2, "码商提现驳回"):
                            self.logger.warning('驳回码商提现退回余额失败:金额{amount},码商{partner_id}, 操作人{admin}'.format(amount=order['amount'], partner_id=order['partner_id'], admin=self.current_user['id']))
                            await conn.rollback()
                            return await self.json_response(data=msg[10007])
                        # 更改状态
                        sql = """update partner_withdraw set status=-1,admin_id=%s where code=%s and status in (0,1)"""
                        if not await cur.execute(sql, (self.current_user['id'], data['code'])):
                            self.logger.warning('驳回码商提现更新订单失败:金额{amount},码商{partner_id}, 操作人{admin}'.format(amount=order['amount'],partner_id=order['partner_id'],admin=self.current_user['id']))
                            await conn.rollback()
                            return await self.json_response(data=msg[10007])
                    except Exception as e:
                        await conn.rollback()
                        return await self.json_response(data=msg[10007])
                    else:
                        await conn.commit()
                        self.logger.warning('驳回码商提现成功:金额{amount},码商{partner_id}, 操作人{admin}'.format(amount=order['amount'],partner_id=order['partner_id'],admin=self.current_user['id']))
                        return await self.json_response(dict(code=20000, msg='操作成功'))
        # 处理
        if data['status'] == 1: # 暂时作废
            if order['payment_type'] is not None and data['payment_type'] != order['payment_type']:
                return await self.json_response(msg[10007])
            if data['payment_type'] == 0:  # 系统出款
                sql = """update partner_withdraw set status=if(amount_order+%s>=amount,2,1),admin_id=%s,
                        payment_type=%s,amount_order=amount_order+%s where code=%s and status in(0,1)"""
                value = [data['amount_order'], self.current_user['id'], data['payment_type'], data['amount_order'],
                         data['code']]
                if not await self.execute(sql, *value):
                    return await self.json_response(msg[10007])
            elif data['payment_type'] == 1:  # 发起代付
                return await self.json_response(msg[10007])
            elif data['payment_type'] in [2, 3]:
                # 拼单
                table = 'partner_recharge' if data['payment_type'] == 2 else 'merchant_recharge'
                sql = """update {table} as r,partner_withdraw as w set r.account=w.account,r.name=w.name,r.type=w.name,
                            r.status=1,w.status=1,w.payment_type=%s,w.amount_order=w.amount_order+r.amount,
                            w.payment_codes=%s,w.admin_id=%s,r.admin_id=%s
                            where r.code=%s and r.status=0 and w.code=%s and w.status in (0,1)""".format(table=table)
                payment_codes = order['payment_codes'] if order['payment_codes'] else ''
                value = [data['payment_type'], payment_codes + data['r_code'] + ',', self.current_user['id'], self.current_user['id'],
                         data['r_code'], data['code']]
                if not await self.execute(sql, *value):
                    return await self.json_response(data=msg[10007])
        if data['status'] == 2:
            if await self.is_null(data, ['amount_order']):
                return await self.json_response(msg[10005])
            if not decimal.Decimal(data['amount_order']) == decimal.Decimal(order['amount']):
                return await self.json_response(data=msg[10007])
            if not await self.update_result('partner_withdraw', {'status': 2, 'admin_id': self.current_user['id']}, {'code': data['code']}):
                self.logger.warning('码商提现确认失败:金额{amount},码商{partner_id}, 操作人{admin}'.format(amount=order['amount'], partner_id=order['partner_id'],admin=self.current_user['id']))
                return await self.json_response(data=msg[10007])
            self.logger.warning('码商提现确认成功:金额{amount},码商{partner_id}, 操作人{admin}'.format(amount=order['amount'],partner_id=order['partner_id'],admin=self.current_user['id']))
        result = dict(code=20000, msg='操作成功')
        return await self.json_response(result)


# 获取商户提现订单
class getWithdrawMerchant(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)

        condition, time_create_between = await self.split_between_condition(data['serchData'], 'time_create')
        condition, time_success_between = await self.split_between_condition(condition, 'time_success')
        between = None
        if time_create_between:
            between = time_create_between
        if not between:
            between = time_success_between

        if (not condition or not condition['code']) and not between:
            between = display_today_between('time_create')
        keys_count = ['amount', 'status']
        data_r, total, count = await self.get_result('merchant_withdraw', ['*'], keys_count, condition, between,
                                                     data['size'], data['page'])
        count_r = {'failOrder': 0, 'successOrder': 0, 'processing': 0, 'amount': decimal.Decimal(0)}
        for i in count:
            if i['status'] == 2:
                count_r['successOrder'] += 1
                count_r['amount'] += i['amount']
            elif i['status'] == -1:
                count_r['failOrder'] += 1
            else:
                count_r['processing'] += 1
        result = dict(code=20000, data=data_r, total=total, count=count_r, msg='获取成功')
        return await self.json_response(result)


# 处理商户提现订单
class handleWithdrawMerchant(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        order = await self.get_result_by_condition('merchant_withdraw', ['admin_id', 'amount', 'status', 'merchant_id'], {'code': data['code']})
        # 驳回
        if data['status'] == -1:
            async with self.application.db.acquire() as conn:
                async with conn.cursor(DictCursor) as cur:
                    try:
                        # 退回余额
                        if not await self.change_balance(conn, cur, 'merchant', order['merchant_id'], order['amount'], data['code'], 2, "驳回提现"):
                            self.logger.warning('商户提现异常={code}, 余额变动错误'.format(code=data['code']))
                            await conn.rollback()
                            return await self.json_response(data=msg[10007])
                        # 更改状态
                        sql = """update merchant_withdraw set status=-1,admin_id=%s where code=%s and status in (0,1)"""
                        if not await cur.execute(sql, (self.current_user['id'], data['code'])):
                            self.logger.warning('商户提现异常={code}, 更新订单出错'.format(code=data['code']))
                            await conn.rollback()
                            return await self.json_response(data=msg[10007])
                    except Exception as e:
                        await conn.rollback()
                        self.logger.warning('商户提现异常={code},非法数据={e}'.format(code=data['code'], e=e))
                        return await self.json_response(data=msg[10007])
                    else:
                        await conn.commit()
                        return await self.json_response(dict(code=20000, msg='操作成功'))
        # 处理
        if data['status'] == 1:
            # 暂时作废
            return await self.json_response(msg[10007])
            if order['payment_type'] is not None and data['payment_type'] != order['payment_type']:
                return await self.json_response(msg[10007])
            if data['payment_type'] == 0:  # 系统出款
                sql = """update merchant_withdraw set status=if(amount_order+%s>=amount,2,1),admin_id=%s,
                                payment_type=%s,amount_order=amount_order+%s where code=%s and status in(0,1)"""
                value = [data['amount_order'], self.current_user['id'], data['payment_type'], data['amount_order'],
                         data['code']]
                if not await self.execute(sql, *value):
                    return await self.json_response(msg[10007])
            elif data['payment_type'] == 1:  # 发起代付
                return await self.json_response(msg[10007])
            elif data['payment_type'] in [2, 3]:
                # 拼单
                table = 'partner_recharge' if data['payment_type'] == 2 else 'merchant_recharge'
                sql = """update {table} as r,merchant_withdraw as w set r.account=w.account,r.name=w.name,r.type=w.name,
                                    r.status=1,w.status=1,w.payment_type=%s,w.amount_order=w.amount_order+r.amount,
                                    w.payment_codes=%s,w.admin_id=%s,r.admin_id=%s
                                    where r.code=%s and r.status=0 and w.code=%s and w.status in (0,1)""".format(
                    table=table)
                payment_codes = order['payment_codes'] if order['payment_codes'] else ''
                value = [data['payment_type'], payment_codes + data['r_code'] + ',', self.current_user['id'], self.current_user['id'],
                         data['r_code'], data['code']]
                if not await self.execute(sql, *value):
                    return await self.json_response(data=msg[10007])
        if data['status'] == 2:
            time_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            if not await self.update_result('merchant_withdraw', {'status': 2, 'admin_id': self.current_user['id'],'time_success':time_now}, {'code': data['code']}):
                return await self.json_response(data=msg[10007])
        result = dict(code=20000, msg='操作成功')
        return await self.json_response(result)
