from application.base import BaseHandler, RewriteJsonEncoder
from application.websocket import monitor

import json


class Websocket(BaseHandler):

    async def post(self):
        try:
            data = json.loads(self.request.body)
            action_type = data.get("type")
            # 构造一个 Websocket 实例来调用其方法
            self.current_user = dict()
            self.current_user['id'] = data.get("admin_id")
            self.qr_id = data.get("qr_id")
            if action_type == 'Login':
                admin_id = data['admin_id']
                admin_pw = data['admin_pw']
                qr_id = data['qr_id']
                login_uuid = data.get('login_uuid', None)
                result = await monitor.Websocket.login(self, admin_id, admin_pw, qr_id, login_uuid)
                return self.write_json(result,None)

            elif action_type == 'Online':
                result = await monitor.Websocket.qrcode_online(self,data['online'], data['o_type'])
                return self.write_json(result,None)

            elif action_type == 'New':
                self.partner_id = data['partner_id']
                result = await monitor.Websocket.new_record(self,data)
                return self.write_json(result,None)

            elif action_type == 'updateBalance':
                await self.update_result('payment', {'balance': data['balance']}, {'id': self.qr_id})

            elif action_type == 'OrderList':
                data_r = await self.get_result_by_condition('payment', ['sys_balance'], {'id': self.qr_id})
                sql = """select sum(amount) as amount from orders_ds where payment_id=%s and status in (3,4) and time_create > curdate()"""
                data_r['ds_balance'] = (await self.query(sql, self.qr_id))[0]['amount']
                sql = """select code,amount,payment_account,payment_name,ifsc from orders_df where payment_id=%s and status in (1,2)"""
                data_r['order_list'] = await self.query(sql, self.qr_id)
                return self.write_json(dict(code=202, data=data_r), RewriteJsonEncoder)

            elif data['type'] == 'Cancelorder':
                result = await monitor.Websocket.cancel_order(self,data['code'])
                return self.write_json(result,None)

            elif data['type'] == 'CheckLogin':
                current_login_uuid = await self.redis.hget('login_uuid', data['qr_id'])
                if data['login_uuid'] != current_login_uuid:
                    return self.write_json({'code': 401, 'data': None, 'message': 'Please log in.'},None)
            else:
                return self.write_json({'code': 400, 'msg': 'Invalid type'},None)

        except Exception as e:
            self.logger.exception(e)
            return self.write_json({'code': 500, 'msg': f'Server error: {e}'},None)

    def write_json(self, response,cls_):
        self.set_header("Content-Type", "application/json")
        if not cls_:
            self.write(json.dumps(response))
        else:
            self.write(json.dumps(response,cls=cls_))