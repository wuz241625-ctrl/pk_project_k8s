import datetime
import json
from decimal import Decimal

from application.base import BaseHandler,RewriteJsonEncoder
import re

# 统计
class getCount(BaseHandler):
    async def post(self):
        data = json.loads(self.request.body)
        if 'time_success' in data.keys() and data['time_success']:
            time_option = 'time_success'
        else:
            time_option = 'time_create'
        data_r = {'order': 0, 'order_success': 0, 'order_fail': 0, 'order_amount': 0, 'order_amount_success': 0,
                  'order_amount_fail': 0, 'order_earn_system': 0, 'order_poundage': 0}
        table = 'orders_ds where' if data['type'] == 'ds' else 'orders_df where parent_id = \'\' and'

        # 查询角色的所有权限name
        role_permissions_sql = f"select name from permissions where status = 1 and id in ({self.current_user['permissions']})"
        role_permission_names_json = await self.query(role_permissions_sql)
        # 字典对象 转 集合
        role_permission_names = set(value for dictionary in role_permission_names_json for value in dictionary.values())
        # 集合中匹配目标，只有管理员才能看
        if ("禁止查看数据统计" in role_permission_names):
            result = dict(code=20000, data=data_r, msg='获取成功')
            return await self.json_response(result)

        # 先取出在统计
        # sql = 'select {keys} from {table} where time_create between %s and %s'.format(
        #     keys='status, amount, earn_system, poundage', table=table)
        sql = 'select {keys} from {table} {option} between %s and %s'.format(
            keys='status, amount, earn_system, poundage', table=table, option=time_option)
        v = data['serchData']
        r = await self.query(sql, *data['serchData'])

        for i in r:
            data_r['order'] += 1
            data_r['order_amount'] += i['amount']
            if i['status'] == -1:
                data_r['order_fail'] += 1
                data_r['order_amount_fail'] += i['amount']
            elif i['status'] >= 3:
                data_r['order_success'] += 1
                data_r['order_amount_success'] += i['amount']
                
                # data_r['order_earn_system'] += i['earn_system']
                # data_r['order_poundage'] += i['poundage']

                # 检查 earn_system 是否为 None
                earn_system_value = i['earn_system'] if i['earn_system'] is not None else Decimal(0)
                data_r['order_earn_system'] += earn_system_value

                # 检查 poundage 是否为 None
                poundage_value = i['poundage'] if i['poundage'] is not None else Decimal(0)
                data_r['order_poundage'] += poundage_value
        # 获取权限值  取缔以下权限识别代码
        # allowAdminProfit = await self.redis.get('allowAdminProfit')
        # if allowAdminProfit:
        #     allowAdminProfit = allowAdminProfit.split(',')
        # # 获取登录管理员id
        # user_id = str(self.get_secure_cookie("user"), 'utf-8')
        # if allowAdminProfit:
        #     # 查看权限是否存在
        #     if not user_id in allowAdminProfit:
        #         data_r['order_earn_system'] = '******'
        #         data_r['order_poundage'] = '******'

        # 使用代收代付权限判断统计权限
        if data['type'] == 'ds':
            if ("禁止查看代收订单手续费" in role_permission_names):
                data_r['order_poundage'] = '******'
            if ("禁止查看代收订单平台利润" in role_permission_names):
                data_r['order_earn_system'] = '******'
        else:
            if ("禁止查看代付订单手续费" in role_permission_names):
                data_r['order_poundage'] = '******'
            if ("禁止查看代付订单平台利润" in role_permission_names):
                data_r['order_earn_system'] = '******'

        result = dict(code=20000, data=data_r, msg='获取成功')
        return await self.json_response(result)


# 代收7日数据统计
class getCountOneW(BaseHandler):
    async def post(self):
        data = json.loads(self.request.body)
        if 'time_success' in data.keys() and data['time_success']:
            time_option = 'time_success'
        else:
            time_option = 'time_create'
        data_r = {
            'order': [0, 0, 0, 0, 0, 0, 0],
            'order_success': [0, 0, 0, 0, 0, 0, 0],
            'order_fail': [0, 0, 0, 0, 0, 0, 0],
            'order_amount': [0, 0, 0, 0, 0, 0, 0],
            'order_amount_success': [0, 0, 0, 0, 0, 0, 0],
            'order_amount_fail': [0, 0, 0, 0, 0, 0, 0],
            'order_earn_system': [0, 0, 0, 0, 0, 0, 0],
            'order_poundage': [0, 0, 0, 0, 0, 0, 0]
        }
        
        # 查询角色的所有权限name
        role_permissions_sql = f"select name from permissions where status = 1 and id in ({self.current_user['permissions']})"
        role_permission_names_json = await self.query(role_permissions_sql)
        # 字典对象 转 集合
        role_permission_names = set(value for dictionary in role_permission_names_json for value in dictionary.values())
        # 集合中匹配目标，只有管理员才能看
        if ("禁止查看代收7日数据统计" in role_permission_names):
            result = dict(code=20000, data=data_r, msg='获取成功')
            return await self.json_response(result)

        date_start = datetime.datetime.combine(datetime.datetime.today().date(), datetime.time())
        
        # sql = 'select {keys} from {table} where time_create between %s and %s'.format(
        #     keys='status, amount, earn_system, poundage, time_create', table=table)
        # sql = 'select {keys} from {table} where {option} between %s and %s'.format(
        #     keys='status, amount, earn_system, poundage, {option}'.format(option=time_option), option=time_option, table=table)
        # v = [date_start - datetime.timedelta(days=7), date_start]
        # r = await self.query(sql, *v)
        # for i in r:
        #     # _k = 6 - (date_start - i['time_create']).days
        #     _k = 6 - (date_start - i[time_option]).days
        #     data_r['order'][_k] += 1
        #     data_r['order_amount'][_k] += i['amount']
        #     if i['status'] == -1:
        #         data_r['order_fail'][_k] += 1
        #         data_r['order_amount_fail'][_k] += i['amount']
        #     elif i['status'] >= 3:
        #         data_r['order_success'][_k] += 1
        #         data_r['order_amount_success'][_k] += i['amount']
        #         # data_r['order_earn_system'][_k] += i['earn_system']
        #         # data_r['order_poundage'][_k] += i['poundage']
        #
        #         # 空判断处理调整20240905
        #         # 检查 earn_system 是否为 None
        #         earn_system_value = i['earn_system'] if i['earn_system'] is not None else Decimal(0)
        #         data_r['order_earn_system'][_k] += earn_system_value
        #
        #         # 检查 poundage 是否为 None
        #         poundage_value = i['poundage'] if i['poundage'] is not None else Decimal(0)
        #         data_r['order_poundage'][_k] += poundage_value
        for i in range(7):
            order_data = await self.get_order(data['type'], date_start - datetime.timedelta(days=7-i), time_option)
            data_r['order'][i] = order_data['order']
            data_r['order_amount'][i] = order_data['order_amount']
            data_r['order_success'][i] = order_data['order_success']
            data_r['order_amount_success'][i] = order_data['order_amount_success']
            data_r['order_fail'][i] = order_data['order_fail']
            data_r['order_amount_fail'][i] = order_data['order_amount_fail']
            data_r['order_earn_system'][i] = order_data['order_earn_system']
            data_r['order_poundage'][i] = order_data['order_poundage']

        # 获取权限值 取缔以下权限识别代码
        # allowAdminProfit = await self.redis.get('allowAdminProfit')
        # if allowAdminProfit:
        #     allowAdminProfit = allowAdminProfit.split(',')
        # # 获取登录管理员id
        # user_id = str(self.get_secure_cookie("user"), 'utf-8')
        # if allowAdminProfit:
        #     # 查看权限是否存在
        #     if not user_id in allowAdminProfit:
        #         data_r['order_earn_system'] = [0, 0, 0, 0, 0, 0, 0]
        #         data_r['order_poundage'] = [0, 0, 0, 0, 0, 0, 0]

        # 使用代收代付权限判断统计权限
        if data['type'] == 'ds':
            if ("禁止查看代收订单手续费" in role_permission_names):
                data_r['order_poundage'] = [0, 0, 0, 0, 0, 0, 0]
            if ("禁止查看代收订单平台利润" in role_permission_names):
                data_r['order_earn_system'] = [0, 0, 0, 0, 0, 0, 0]
        else:
            if ("禁止查看代付订单手续费" in role_permission_names):
                data_r['order_poundage'] = [0, 0, 0, 0, 0, 0, 0]
            if ("禁止查看代付订单平台利润" in role_permission_names):
                data_r['order_earn_system'] = [0, 0, 0, 0, 0, 0, 0]

        result = dict(code=20000, data=data_r, msg='获取成功')
        return await self.json_response(result)

    async def get_order(self, type, date_start, option):
        tableKey = 'orders_ds' if type == 'ds' else 'orders_df'
        table = 'orders_ds where' if type == 'ds' else 'orders_df where parent_id = \'\' and'
        
        key = 'getCountOneW_{table}_{option}_{time}'.format(table=tableKey,option=option,time=date_start.strftime("%Y%m%d"))
        if await self.redis.exists(key):
            data = json.loads(await self.redis.get(key))
            return {k: float(v) if re.search(r'[.]', str(v)) else int(v) for k, v in data.items()}
        else:
            sql = """select count(1) AS 'order',
                    COALESCE(SUM(amount), 0) AS order_amount,
                    COALESCE(SUM(CASE WHEN status = -1 THEN 1 ELSE 0 END), 0)  AS order_fail,
                    COALESCE(SUM(CASE WHEN status = -1 THEN amount ELSE 0 END), 0) AS order_amount_fail,
                    COALESCE(SUM(CASE WHEN status >= 3 THEN 1 ELSE 0 END), 0)  AS order_success,
                    COALESCE(SUM(CASE WHEN status >= 3 THEN amount ELSE 0 END), 0) AS order_amount_success,
                    COALESCE(SUM(CASE WHEN status >= 3 and earn_system IS NOT NULL THEN earn_system ELSE 0 END), 0) AS order_earn_system,
                    COALESCE(SUM(CASE WHEN status >= 3 and poundage IS NOT NULL THEN poundage ELSE 0 END), 0)   AS order_poundage
                    from {table} {option} between %s and %s """.format(table = table,option = option)
            value = [date_start,date_start + datetime.timedelta(days=1)]
            data  = await self.query(sql, *value)
            date_end = datetime.datetime.combine(datetime.datetime.today().date(), datetime.time())
            await self.redis.set(key,json.dumps(data[0],cls=RewriteJsonEncoder),ex=((8-(date_end-date_start).days)*24*60*60))
            return data[0]

# 商户码商余额
class getBalance(BaseHandler):
    async def post(self):
        data = json.loads(self.request.body)
        sql = """select *,sum(balance_m+balance_m_frozen+balance_p+balance_p_frozen+balance_p_deposit) as amount
                    from balance_count_record group by id order by id desc limit %s offset %s"""
        value = [data['size'], (data['page'] - 1) * data['size']]
        data_r = await self.query(sql, *value)
        sql = """select sum(balance) as balance_p, sum(balance_frozen)as balance_p_frozen ,sum(balance_deposit)as balance_p_deposit from partner"""
        count = (await self.query(sql))[0]
        # 商户余额、冻结余额暂不统计id为36、41、192的商户 + '312'
        sql = """select sum(balance) as balance_m, sum(balance_frozen)as balance_m_frozen from merchant where id not in ('36','41','192', '312')"""
        self.logger.info(f" getBalance: {sql}")
        r = (await self.query(sql))[0]
        count.update(r)
        sql = """select sum(balance) as balance_p_inside, sum(balance_frozen)as balance_p_frozen_inside from partner where type = 0"""
        inside = (await self.query(sql))[0]
        count.update(inside)
        sql = """select sum(balance) as balance_p_outside, sum(balance_frozen)as balance_p_frozen_outside from partner where type = 1"""
        outside = (await self.query(sql))[0]
        count.update(outside)
        # count['balance'] = count['balance_p'] + count['balance_m'] 报错
        self.logger.info(f" balance_m: {count['balance_p']}")
        self.logger.info(f" balance_m: {count['balance_m']}")
        count['balance'] = Decimal(count['balance_p']) + Decimal(count['balance_m'])
        result = dict(code=20000, data=data_r, count=count, msg='获取成功')
        return await self.json_response(result)


# 财务日报
class getDaily(BaseHandler):
    async def post(self):
        data = json.loads(self.request.body)
        condition, between = await self.split_between_condition(data['serchData'], 'date')
        data_r, total, count_date = await self.get_result('daily', ['amount', 'balance_type', 'record_type', 'date'],
                                                          ['amount', 'balance_type', 'record_type'], condition,
                                                          between, data['size'], data['page'])
        count = [0, 0, 0]
        for i in count_date:
            count[2] += i['amount']
            count[i['balance_type']] += i['amount']

        result = dict(code=20000, data=data_r, count=count, total=total, msg='获取成功')
        return await self.json_response(result)


# 操作统计
class getAdmingoperate(BaseHandler):
    async def post(self):
        data = json.loads(self.request.body)
        condition, between = await self.split_between_condition(data['serchData'], 'time_create')
        data_r = await self.get_results_no_condition('admin', ['id'])
        # 默认值
        for i in data_r:
            # i['change'] = 0
            # i['change_amount'] = Decimal(0)
            # i['transfer'] = 0
            # i['transfer_amount'] = Decimal(0)
            # i['recharge'] = 0
            # i['recharge_amount'] = Decimal(0)
            # i['withdraw'] = 0
            # i['withdraw_amount'] = Decimal(0)
            sql = """select count(id) as count from operate where admin_id=%s and type=11 and time_create>curdate()"""
            r = await self.query(sql, i['id'])
            i['ds'] = r[0]['count']
            sql = """select count(id) as count from operate where admin_id=%s and type=12 and time_create>curdate()"""
            r = await self.query(sql, i['id'])
            i['df'] = r[0]['count']
        tables = ['balance_record', 'balance_record_df', 'merchant_transfer', 'partner_transfer', 'merchant_recharge',
                  'partner_recharge', 'merchant_withdraw', 'partner_withdraw']
        # for i in tables:
        #     data_r = await self.count(i, between, data_r)
        result = dict(code=20000, data=data_r, msg='获取成功')
        return await self.json_response(result)

    async def count(self, table, between, data):
        sql = """select admin_id,count(id) as c,sum(amount) as amount from {table} where admin_id is not null""".format(
            table=table)
        if table in ['balance_record', 'balance_record_df']:
            sql += " and  record_type=5"
        value = []
        if between:
            bt_key, bt_start, bt_end = await self.dict_to_between(between)
            sql += " and " + bt_key
            value += [bt_start, bt_end]
        sql += " group by admin_id"
        r = await self.query(sql, *value)
        if r:
            key = 'change'
            if table in ['merchant_transfer', 'partner_transfer']:
                key = 'transfer'
            elif table in ['merchant_recharge', 'partner_recharge']:
                key = 'recharge'
            elif table in ['merchant_withdraw', 'partner_withdraw']:
                key = 'withdraw'
            for i in data:
                for j in r:
                    if i['id'] == j['admin_id']:
                        i[key] += j['c']
                        i[key + '_amount'] += j['amount']
            return data
        return data


# 操作日志
class getOperate(BaseHandler):
    async def post(self):
        data = json.loads(self.request.body)
        between = {}
        if 'between' not in data:
            data['between'] = None
        else:
            between['key'] = "created"
            between['start'] = data['between'][0]
            between['end'] = data['between'][1]
        data_r, total = await self.get_result('operate', ['*'], None, data['serchData'], between, data['size'],
                                              data['page'])
        result = dict(code=20000, data=data_r, total=total, msg='获取成功')
        return await self.json_response(result)
