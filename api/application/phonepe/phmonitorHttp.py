import json
from application.base import BaseHandler
from application.phonepe import phmonitor

class PaymentInfoMixin:
    async def load_payment_info(self, data):
        # 一定先设置 payment_id
        self.payment_id = data['payment_id']

        # 如果关键字段都已存在，说明已经加载过，跳过
        if all([
            hasattr(self, 'partner_id'),
            hasattr(self, 'bank_type'),
            hasattr(self, 'qr_channels')
        ]):
            return  # 已加载，跳过查询

        # 加载 payment 信息
        payment_keys = ['partner_id', 'status', 'certified', 'account_type', 'bank_type_id', 'channel', 'phone']
        payment = await self.get_result_by_condition('payment', payment_keys, {'id': self.payment_id})

        if not hasattr(self, 'partner_id'):
            self.partner_id = payment['partner_id']

        if not hasattr(self, 'bank_type'):
            # 加载 bank_type
            bank_type = await self.get_result_by_condition(
                'bank_type',
                ['id', 'name'],
                {'id': payment['bank_type_id']}
            )
            self.bank_type = bank_type['name']

        if not hasattr(self, 'qr_channels'):
            self.qr_channels = payment['channel'].split(',') if payment['channel'] else []
          
class LoginHandler(BaseHandler):
    async def post(self):
        # monitor = phmonitor()
        data = json.loads(self.request.body)
        # 调用原来的 self.login(data)
        result = await phmonitor.Websocket.login(self, data)
        self.write(result)
    
class OnlineHandler(PaymentInfoMixin, BaseHandler):
    async def post(self):
        try:
            self.logger.info(f"OnlineHandler： {self.request.body}")
            data = json.loads(self.request.body)
            self.logger.info(f"[parameter]: {data}")
            
            await self.load_payment_info(data)
            
            result = await phmonitor.Websocket.qrcode_online(self, data.get('online'))
            self.write(result)
        except Exception as e:
            self.logger.error(f"OnlineHandler Error: {str(e)}")
            self.write(dict(type='Online', code=500, msg='internal error'))
    
class OfflineHandler(PaymentInfoMixin, BaseHandler):
    async def post(self):
        try:
            data = json.loads(self.request.body)
            
            await self.load_payment_info(data)
             
            result = await phmonitor.Websocket.logout(self, True)
            self.write(result)
        except Exception as e:
            self.logger.error(f"OfflineHandler Error: {str(e)}")
            self.write(dict(type='Offline', code=500, msg='internal error'))
    
class UpiHandler(BaseHandler):
    async def post(self):
        try:
            data = json.loads(self.request.body)
            upi = data.get('upi')
            payment_id = data.get('payment_id')

            if not upi or not payment_id:
                self.write(dict(type='UPI', code=99, msg='missing upi or payment_id'))
                return

            result = await self.get_result_by_condition('payment', ['upi'], {'id': payment_id})

            if not result or result['upi'] != upi:
                success = await self.update_result('payment', {'upi': upi}, {'id': payment_id})
                if not success:
                    self.write(dict(type='UPI', code=200, msg='update upi error.'))
                    return

            self.write(dict(type='UPI', code=200, msg='update upi success.'))
        except Exception as e:
            self.logger.error(f"UpiHandler Error: {str(e)}")
            self.write(dict(type='UPI', code=500, msg='internal error'))

class NewHandler(BaseHandler, PaymentInfoMixin):
    async def post(self):
        try:
            data = json.loads(self.request.body)
            # 调用原来 WebSocket 中的 self.new_record 方法逻辑
            await self.load_payment_info(data)
            # 如果 new_record 是外部函数，请将其提取出来导入并调用
            result = await phmonitor.Websocket.new_record(self, data)
            print(f'result NewHandler : {result}')
            self.write(result)
        except Exception as e:
            self.logger.error(f"NewHandler Error: {str(e)}")
            self.write(dict(type='New', code=500, msg='internal error'))