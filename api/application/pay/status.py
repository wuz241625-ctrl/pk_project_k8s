from application.sign import SignatureAndVerification
from application.base import BaseHandler
from application.message import msg


class Status_ds(BaseHandler):
    """代收订单查询"""

    async def post(self):
        """数据通过post form-data 方式提交"""
        try:
            data = {k: self.get_argument(k) for k in self.request.arguments}
            self.data_receive_filter_xss = {k: await self.get_escaped_argument(k) for k in self.request.arguments}
        except Exception:
            self.logger.exception('参数异常')
            return await self.json_response(msg[10001])
        self.logger.info('pay status 收到参数{data}'.format(data=str(data)))

        # 检查提交参数是否合规
        valid_keys = ['mer_id', 'order_id', 'sign']

        if not await self.is_valid_key(data, valid_keys):
            return await self.json_response(data=msg[10002])

        # 检查空参数
        if await self.is_null(data, valid_keys):
            return await self.json_response(data=msg[10003])

        # 检查参数非法
        if not await self.check_different(data, self.data_receive_filter_xss, valid_keys):
            self.logger.info('pay 参数非法{data}'.format(data=str(data)))
            return await self.json_response(data=msg[10002])

        try:
            merchant_id = int(data['mer_id'])
            merchant_code = data['order_id']
        except Exception as e:
            self.logger.exception(e)
            return await self.json_response(data=msg[10002])

        # 获取商户信息
        merchant = await self.get_result_by_condition('merchant', ['mc_key', 'status'], {'id': merchant_id})
        if not merchant:
            return await self.json_response(data=msg[10004])

        # 验签
        if not await self.check_sign(data, merchant['mc_key']):
            return await self.json_response(msg[10006])

        # 检查商户是否正常
        if merchant['status'] == 0:
            return await self.json_response(msg[10005])
        keys = ['code', 'amount', 'realpay', 'status', 'time_create', 'time_success', 'time_updated', 'utr', 'upi']
        r = await self.get_result_by_condition('orders_ds', keys, {'merchant_code': merchant_code})
        if not r:
            return await self.json_response(msg[10016])
        ret = dict(code=0, message='')
        data = dict(
            order_id=merchant_code,
            order_code=r['code'],
            amount=r['amount'],
            realpay=r['realpay'],
            utr=r['utr'],
            upi=r['upi'],
            time_create=r['time_create'],
            time_finish=r['time_success'],
            status=r['status']
        )
        if data['status'] in [3, 4]:
            data['status'] = 0  # 成功
        elif data['status'] in [0, 1, 2]:
            data['status'] = 1  # 处理中
        else:
            data['status'] = 2
            data['time_finish'] = r['time_updated']
        ret['data'] = data
        return await self.json_response(ret)

    @staticmethod
    async def check_sign(data, key):
        try:
            sign = data['sign']
            if SignatureAndVerification.md5_verify(data, sign, key):
                return True
            else:
                return False
        except Exception:
            return False


class Balance(BaseHandler):
    """余额查询"""

    async def post(self):
        """数据通过post form-data 方式提交"""
        try:
            self.data_receive = {k: self.get_argument(k) for k in self.request.arguments}
            self.data_receive_filter_xss = {k: await self.get_escaped_argument(k) for k in self.request.arguments}
        except Exception as e:
            self.logger.exception('参数异常')
            return await self.json_response(msg[10001])
        self.logger.info('balance 收到参数{data}'.format(data=str(self.data_receive)))

        valid_keys = ['mer_id', 'sign']
        require_keys = valid_keys
        # 检查提交参数是否合规
        if not await self.is_valid_key(self.data_receive, valid_keys):
            return await self.json_response(data=msg[10002])

        # check null args
        if await self.is_null(self.data_receive, require_keys):
            return await self.json_response(data=msg[10003])

        if not await self.check_different(self.data_receive, self.data_receive_filter_xss, require_keys):
            self.logger.info('balance 参数非法{data}'.format(data=str(self.data_receive)))
            return await self.json_response(data=msg[2])

        try:
            merchant_id = int(self.data_receive['mer_id'])
        except Exception as e:
            self.logger.exception(e)
            return await self.json_response(data=msg[10001])

        # 获取商户信息
        keys = ['balance', 'balance_frozen', 'status', 'mc_key']
        _merchant_info = await self.get_result_by_condition('merchant', keys, {'id': merchant_id})
        if not _merchant_info:
            return await self.json_response(data=msg[10004])

        # 验签
        if not await self.check_sign(self.data_receive, _merchant_info['mc_key']):
            return await self.json_response(msg[10006])

        # 检查商户是否正常
        if _merchant_info['status'] == 0:
            return await self.json_response(msg[10005])

        ret = dict(
            code=0,
            message=''
        )
        data = dict(
            available=_merchant_info['balance'],
            frozen=_merchant_info['balance_frozen'],
            balance=_merchant_info['balance'] + _merchant_info['balance_frozen']
        )
        ret['data'] = data
        return await self.json_response(ret)

    async def check_sign(self, data, key):
        try:
            sign = self.data_receive['sign']
            if SignatureAndVerification.md5_verify(data, sign, key):
                return True
            else:
                return False
        except Exception as e:
            return False


class Status_df(BaseHandler):
    """代付订单查询"""

    async def post(self):
        """数据通过post form-data 方式提交"""
        try:
            data = {k: self.get_argument(k) for k in self.request.arguments}
            self.data_receive_filter_xss = {k: await self.get_escaped_argument(k) for k in self.request.arguments}
        except Exception:
            self.logger.exception('参数异常')
            return await self.json_response(msg[10001])
        self.logger.info('pay status 收到参数{data}'.format(data=str(data)))

        # 检查提交参数是否合规
        valid_keys = ['mer_id', 'order_id', 'sign']

        if not await self.is_valid_key(data, valid_keys):
            return await self.json_response(data=msg[10002])

        # 检查空参数
        if await self.is_null(data, valid_keys):
            return await self.json_response(data=msg[10003])

        # 检查参数非法
        if not await self.check_different(data, self.data_receive_filter_xss, valid_keys):
            self.logger.info('pay 参数非法{data}'.format(data=str(data)))
            return await self.json_response(data=msg[10002])

        try:
            merchant_id = int(data['mer_id'])
            merchant_code = data['order_id']
        except Exception as e:
            self.logger.exception(e)
            return await self.json_response(data=msg[10002])

        # 获取商户信息
        merchant = await self.get_result_by_condition('merchant', ['mc_key', 'status'], {'id': merchant_id})
        if not merchant:
            return await self.json_response(data=msg[10004])

        # 验签
        if not await self.check_sign(data, merchant['mc_key']):
            return await self.json_response(msg[10006])

        # 检查商户是否正常
        if merchant['status'] == 0:
            return await self.json_response(msg[10005])
        keys = ['code', 'amount', 'realpay', 'status', 'time_create', 'time_success', 'time_updated', 'payment_account',
                'payment_name', 'payment_bank', 'utr']
        r = await self.get_result_by_condition('orders_df', keys, {'merchant_code': merchant_code})
        if not r:
            return await self.json_response(msg[10016])
        ret = dict(code=0, message='')
        data = dict(
            order_id=merchant_code,
            order_code=r['code'],
            amount=r['amount'],
            utr=r['utr'],
            realpay=r['realpay'],
            time_create=r['time_create'],
            time_finish=r['time_success'],
            status=r['status'],
            user=r['payment_name'],
            account=r['payment_account'],
            bank=r['payment_bank']
        )
        if data['status'] in [3, 4]:
            data['status'] = 0  # 成功
        elif data['status'] in [0, 1, 2]:
            data['status'] = 1  # 处理中
        else:
            data['status'] = 2
            data['time_finish'] = r['time_updated']
        ret['data'] = data
        return await self.json_response(ret)

    @staticmethod
    async def check_sign(data, key):
        try:
            sign = data['sign']
            if SignatureAndVerification.md5_verify(data, sign, key):
                return True
            else:
                return False
        except Exception:
            return False
