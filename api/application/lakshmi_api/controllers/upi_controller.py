from application.crypto import decrypt
from application.lakshmi_api.base import BaseHandler, ApiError, ApiInfo
import json
import bcrypt

from datetime import datetime, timedelta

from sqlalchemy import update, and_, text
from sqlalchemy.orm import joinedload

from application.lakshmi_api.base import BaseHandler, ApiError
from application.lakshmi_api.enums.payment_login_progress import string_to_enum, PaymentLoginProgress
from application.lakshmi_api.error_handler import handle_errors
from application.lakshmi_api.models import *
from application.lakshmi_api.models.payment import Payment
from application.lakshmi_api.schema.payment_schema import *
from application.lakshmi_api.services.pagination_service import PaginationService
from application.lakshmi_api.services.payment_services import BANK_SERVICES
from application.lakshmi_api.services.payments.amazon_pay_service import AmazonService
from application.easypaisa_runtime.reader import EasyPaisaRuntimeReader
from application.utils import StringUtils
from constants import RedisKeys
from application.lakshmi_api.exceptions.api_error import NewApiError
from application.app.login.banks.easypaisa import EasyPaisa
  
# 各银行输入OTP的位数
OTP_DIGITS = {
    'PHONEPE': 5,
    'FREECHARGE': 4,
    'MOBIKWIK': 6,
    'AIRTEL': 4,
    'AMAZON': 0,
    'INDUS': 6,
    'ULCASH': 6,
    'JIO': 6,
    'MAHA': 0
}
PAYMENT_STATUS = {0: 'inactive', 1: 'active'}
CERTIFIED_STATUS = {'inactive': 0, 'active': 1}


class UpiHandler(BaseHandler):
    def _get_params(self, keys):
        params = {}
        for key in keys:
            params[key] = self.get_body_argument(key, default=None)
        return params

    async def _assign_bank(self, bank_id):
        with self.db_orm.sessionmaker() as session:
            bank = session.query(BankType).filter_by(id=bank_id).first()
            if bank is not None:
                return bank

            raise NewApiError('10201')  # Bank not found

    async def _assign_payment(self, payment_id):
        with self.db_orm.sessionmaker() as session:
            payment = (
                session.query(Payment)
                .options(joinedload(Payment.bank))
                .filter(Payment.id == payment_id, Payment.user_id == self.current_user.id)
                .first()
            )
        if payment is not None:
            return payment

        raise NewApiError('10301')  # Payment not found or access denied

    """
    根据银行id，查询银行名
    """
    async def _get_bank_type_name(self, bank_type_id):
        with self.db_orm.sessionmaker() as session:
            # 查询orders_ds表
            get_bank_type_name_sql = f"""
                select name from bank_type where id = :id
            """
            result_get_bank_type_name = session.execute(text(get_bank_type_name_sql), {'id': bank_type_id}).fetchone()

        if result_get_bank_type_name is not None :
            return result_get_bank_type_name[0]
        return None

    """
    统计代收订单、代付订单中，3小时内过期的订单数
    """
    async def _count_orders_ds_within_3hours(self, payment_id, bank_type_id):

        check_bank_names = {"AIRTEL","PHONEPE","AMAZON"}
        # 检查传入的银行id，是否存在于要检查的银行中
        bank_type_name = await self._get_bank_type_name(bank_type_id)
        if bank_type_name is None:
            raise NewApiError('10201')  # Bank not found
        if bank_type_name not in check_bank_names:
            return 0

        now = datetime.now()
        three_hours_ago = now - timedelta(hours=3)
        with self.db_orm.sessionmaker() as session:
            # 查询orders_ds表
            count_orders_ds_sql = f"""
                select count(1) 
                from orders_ds 
                inner join payment on payment.id = orders_ds.payment_id
                inner join bank_type on bank_type.id = payment.bank_type
                where orders_ds.payment_id = :payment_id 
                and orders_ds.status =-1 
                and orders_ds.time_create >= :time_create
            """
            result_count_orders_ds = session.execute(text(count_orders_ds_sql), {'payment_id': payment_id, 'time_create': three_hours_ago}).fetchone()

        if result_count_orders_ds is not None :
            return result_count_orders_ds[0]
        return 0

    """
    统计代收订单、代付订单中，3小时内过期的订单数
    """
    async def _count_orders_df_within_3hours(self, payment_id, bank_type_id):

        check_bank_names = {"AIRTEL","PHONEPE","AMAZON"}
        # 检查传入的银行id，是否存在于要检查的银行中
        bank_type_name = await self._get_bank_type_name(bank_type_id)
        if bank_type_name is None:
            raise NewApiError('10201')  # Bank not found
        if bank_type_name not in check_bank_names:
            return 0

        now = datetime.now()
        three_hours_ago = now - timedelta(hours=3)
        with self.db_orm.sessionmaker() as session:
            # 查询orders_df表
            count_orders_df_sql = f"""
                select count(1) 
                from orders_df 
                inner join payment on payment.id = orders_df.payment_id
                inner join bank_type on bank_type.id = payment.bank_type
                where orders_df.payment_id = :payment_id 
                and orders_df.status =-1 
                and orders_df.time_create >= :time_create
            """
            result_count_orders_df = session.execute(text(count_orders_df_sql), {'payment_id': payment_id, 'time_create': three_hours_ago}).fetchone()
        if result_count_orders_df is not None :
            return result_count_orders_df[0]
        return 0

    async def _check_place_order_status(self, payment_id):
        reader = EasyPaisaRuntimeReader(self.redis)
        return await reader.is_place_order_online(payment_id)

    async def _check_selling_order_status(self, payment_id):
        reader = EasyPaisaRuntimeReader(self.redis)
        return await reader.is_selling_order_online(payment_id)

    async def _collection_online_payment_ids(self):
        reader = EasyPaisaRuntimeReader(self.redis)
        payment_ids = set()
        for value in await self.redis.smembers('payment_online_ds'):
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            payment_ids.add(str(value).strip())
        payment_ids.update(await reader.collection_online_payment_ids())
        return sorted(payment_id for payment_id in payment_ids if payment_id)

    async def _upi_online_status_via_redis(self, bank_name, payment_id):
        # TODO: fix the hardcode, base on php side not match db bank name
        if bank_name in ['PHONEPE', 'FREECHARGE', 'AIRTEL', 'AMAZON', 'JIO']:
            key = f"login_on_{bank_name.lower()}_{payment_id}"
        elif bank_name in ['MOBIKWIK']:
            key = f"login_on_mobi_{payment_id}"

        result = await self.redis.get(key)
        return result is not None

    """
    检查银行下upi是否重复
    """
    async def _check_bank_upi_is_repeat(self, payment_id, bank_id, upi):
        with self.db_orm.sessionmaker() as session:
            payment = (
                session.query(Payment)
                .options(joinedload(Payment.bank))
                .filter(Payment.bank_type_id == bank_id, Payment.upi == upi)
                .first()
            )
        if payment is not None and payment.id != int(payment_id):
            return True
        return False

    @staticmethod
    def _verify_payment_password_bcrypt(password, hashed_password):
        if not bcrypt.checkpw(password.encode('utf8'), hashed_password.encode('utf8')):
            raise NewApiError('10202')  # Payment Password Incorrect (Authentication error)

class NewUpi(UpiHandler):
    @handle_errors
    async def get(self):
        await self.authenticate_current_user()
        # 是否正式环境，否则为内部测试
        is_formal = self.get_query_argument('is_formal', "1")
        with self.db_orm.sessionmaker() as session:
            if is_formal == "1":
                bank_types = session.query(BankType).filter(BankType.status == 1, BankType.genre == 1).all()
            else:
                bank_types = session.query(BankType).filter(BankType.status == 1).all()
        self.write({
            "data": {
                "banks": UpiBankSchema(many=True).dump(bank_types),
                "create_path": "/api/v1/user/upi"
            }})


class Upi(UpiHandler):
    @handle_errors
    async def get(self):
        await self.authenticate_current_user()
        self.logger.info("Request [GET] (/user/upi), user: %s, name: %s", self.current_user.id, self.current_user.name)
        # 是否正式环境，否则为内部测试
        is_formal = self.get_query_argument('is_formal', "1")
        with self.db_orm.sessionmaker() as session:
            if is_formal == "1":
                bank_types = session.query(BankType).filter(BankType.status == 1, BankType.genre == 1).all()
            else:
                bank_types = session.query(BankType).filter(BankType.status == 1).all()
            bank_types_ids = [obj.id for obj in bank_types]
            where_clause = and_(Payment.user_id == self.current_user.id,
                                Payment.bank_type_id.in_(bank_types_ids))

            total_count = session.query(Payment).filter(where_clause).count()
            pagination_service = PaginationService(self.request.path, self.request)
            offset, limit, pagination_data = await pagination_service.get_pagination_data(total_count)

            payments = session.query(Payment).filter(where_clause) \
                .options(joinedload(Payment.bank)) \
                .offset(offset) \
                .limit(limit) \
                .all()
            payment_ids = [obj.id for obj in payments]

            today_order_summary = WithdrawOrder.get_today_order_summary(session, payment_ids)

            orders_summary = {payment_id: {"total_orders": total, "success_orders": success, "fail_orders": fail} for
                              payment_id, total, success, fail in today_order_summary}
            for payment in payments:
                payment.today_withdraw_order_summary = orders_summary.get(payment.id)
                # maha银行时，重置upi为phone
                if "maha" == payment.bank.name.lower():
                    payment.upi = payment.phone

        upi_bank_schema = UpiBankSchema(many=True)
        raw_payments = UpiPaymentSummarySchema(many=True).dump(payments)
        with_payment_status = await self.set_lock_status_from_redis(raw_payments)
        # 第一状态（正常）
        # selling_order_status = true 并且 lock_status = false 并且 died_status = false
        # 第二状态（需要等待）
        # selling_order_status = false 并且 payment_upi_active_expire_seconds >0 并且 lock_status = false 并且 died_status = false
        # 第三状态（需要重新登录，并再次抓取）
        # selling_order_status = false 并且 payment_upi_active_expire_seconds <= 0 并且 lock_status = false 并且 died_status = false
        # 第四状态（临时锁定 lock_status = true 并且 died_status = false）
        # 第五状态（永久锁定 died_status = true）
        sorted_payments = sorted(with_payment_status, key=lambda x: (x['died_status'], x['lock_status'], -x['selling_order_status'], x['payment_upi_active_expire_seconds']))
        banks = upi_bank_schema.dump(bank_types)

        response_data = {
            "data": {
                "banks": banks,
                "payments": sorted_payments
            },
            "pagination": pagination_data
        }
        self.logger.info("Response [GET] (/user/upi), user: %s, name: %s, responseData: %s", self.current_user.id, self.current_user.name, response_data)
        self.write(response_data)

    async def set_lock_status_from_redis(self, payments):
        self.logger.info("[METHOD] set_lock_status_from_redis() INTO, user: %s, name: %s, payments: %s", self.current_user.id, self.current_user.name, payments)
        with self.db_orm.sessionmaker() as session:
            for payment in payments:
                service_class = BANK_SERVICES[payment['bank_name']]
                service = service_class(session, self.redis, self.redis_pub, self.logger)
                payment['place_order_status'] = await self._check_place_order_status(payment['id'])
                payment['selling_order_status'] = await service.selling_order_status(payment['id'])

                # 锁定状态
                order_ttl = 0
                send_order_ttl = 0
                formatted_expire_time = ''
                redis_key = f"orders_ds_limit_{payment['id']}"
                orders_lock_status = (await self.redis.get(redis_key) is not None)
                if orders_lock_status :
                    order_ttl = await self.redis.ttl(redis_key)

                redis_key = f"send_orders_ds_limit_{payment['id']}"
                send_orders_lock_status =(await self.redis.get(redis_key) is not None)
                if send_orders_lock_status :
                    send_order_ttl = await self.redis.ttl(redis_key)

                ttl = (send_order_ttl if send_order_ttl > order_ttl else order_ttl)
                if ttl > 0 :
                    # 当前时间
                    current_time = datetime.now()
                    # 计算过期时间：当前时间 + TTL秒数
                    expire_time = current_time + timedelta(seconds=ttl)
                    # 将过期时间转换为所需的格式: yyyy-MM-dd hh:mm:ss
                    formatted_expire_time = expire_time.strftime('%Y-%m-%d %H:%M:%S')

                payment['lock_status'] = orders_lock_status or send_orders_lock_status
                payment['lock_expire_time'] = formatted_expire_time

                # 死码状态
                payment['died_status'] = payment['manual_status']
                payment['payment_upi_active_expire_seconds'] = (await self.redis.ttl(f"upi_active_payment:{payment['id']}"))

        self.logger.info("[METHOD] set_lock_status_from_redis() return, user: %s, name: %s, payments: %s",
                         self.current_user.id, self.current_user.name, payments)
        return payments

    @handle_errors
    async def post(self):
        await self.authenticate_current_user()
        await self.log_user_and_ip('用户操作新增upi')
        if self.current_user.genre == 0:
            self.logger.warning(
                "Response [POST] (/user/upi), 用户为内部码商,无新增upi权限 user_id: %s",
                self.current_user.id
            )
            raise ApiError("Cannot add UPI.please contact support.")

        params = self._get_params(['bank_id', 'phone', 'name', 'pin', 'mpin', 'tpin', 'account', 'mock', 'payment_password'])

        # 处理保存登录pin
        if not params.get("pin", None):
            params['pin'] = ''
        if params.get("mpin", None) and not params.get("pin", None):
            params['pin'] = params.get("mpin")

        # 处理接收交易pin
        if not params.get("tpin", None):
            params['tpin'] = ''
        else:
            # 对接收到的tpin进行解密
            params['tpin'] = decrypt(params['tpin'])

        if params['account'] is None:
            params['account'] = ''

        # verify payment password
        if not params.get("payment_password", None):
            params['payment_password'] = ''
        
        try:
            self._verify_payment_password_bcrypt(params['payment_password'], self.current_user.hash_trade)
        except NewApiError:
            raise NewApiError('10202')  # 认证错误
            
        params.pop('payment_password', None)  # 移除 'mock' 键，如果不存在则不报错
        self.logger.info("Request [POST] (/user/upi), user: %s, name: %s, params.bank_id: %s, params.phone: %s, params.name: %s, params.pin: %s, params.tpin: %s",
                         self.current_user.id, self.current_user.name, params['bank_id'], params['phone'], params['name'], params['pin'], params['tpin'])
        upi = CreateUpiSchema().load(params)

        bank = await self._assign_bank(int(upi["bank_id"]))

        with self.db_orm.sessionmaker() as session:
            check_upi = session.query(Payment).filter(and_(Payment.bank_type_id == int(upi["bank_id"]),
                                                           Payment.phone == upi["phone"])).first()
            if check_upi is not None:
                if check_upi.user_id == self.current_user.id:
                    self.logger.error("Response [POST] (/user/upi), user: %s, name: %s, errorMsg: %s", self.current_user.id,
                                     self.current_user.name, 'This is your UPI. Please active it in UPI list')
                    raise NewApiError('10401')  # UPI已存在且属于当前用户
                else:
                    self.logger.error("Response [POST] (/user/upi), user: %s, name: %s, errorMsg: %s", self.current_user.id,
                                     self.current_user.name, 'Upi already exists')
                    raise NewApiError('10402')  # UPI已被占用

            new_upi = Payment(
                user_id=self.current_user.id,
                bank_type=upi["bank_id"],
                name=upi["name"],
                phone=upi["phone"],
                bank_type_id=int(upi["bank_id"]),
                account_type=0,
                pin=upi["pin"],
                tpin=upi["tpin"],
                account=upi["account"],
            )
            session.add(new_upi)
            session.commit()
            new_upi = session.query(Payment).options(joinedload(Payment.bank)).filter_by(id=new_upi.id).one()

            service_class = BANK_SERVICES[new_upi.bank.name]
            service = service_class(self.db_orm, self.redis, self.redis_pub, self.logger)

            payment_schema = UpiPaymentSchema().dump(new_upi)
            self.logger.info("Response [POST] (/user/upi), user: %s, name: %s, payment_schema: %s", self.current_user.id,
                             self.current_user.name, payment_schema)
            # 需要发送OTP
            if not payment_schema['bank']['in_app_browser']:
                self.logger.info("Response [POST] (/user/upi), user: %s, name: %s, new_upi: %s",
                                 self.current_user.id,
                                 self.current_user.name, new_upi)
                try:
                    await service.send_otp(new_upi)
                except Exception as e:
                    self.logger.error(f"Failed to send OTP: {str(e)}")
                    raise NewApiError('10403')  # Failed to send OTP
                    
                otp_digits = OTP_DIGITS.get(new_upi.bank.name, 4)
                if payment_schema['bank']['name'] != 'MAHA':
                    otp = True
                else:
                    otp = False
            # 不需要发送OTP
            else:
                otp = False
                otp_digits = 0

            """标记payment本地模拟测试 10分钟"""
            if "mock" in params and "1" == params.get("mock"):
                await self.redis.set(name=f"payment_mock:{new_upi.id}", value="1", ex=600)

            responseData = {
                "data": {
                    "payment": payment_schema,
                    "otp": otp,
                    "otp_digits": otp_digits,
                    "active_path": f"/api/v1/user/upi/{new_upi.id}/active",
                    "cookie_path": f"/api/v1/user/upi/{new_upi.id}/cookie",
                    "status": new_upi.status
                }
            }
            self.logger.info("Response [POST] (/user/upi), user: %s, name: %s, responseData: %s", self.current_user.id,
                             self.current_user.name, responseData)
            self.write(responseData)


class UpiAccounts(UpiHandler):
    @handle_errors
    async def get(self, payment_id):
        await self.authenticate_current_user()
        payment = await self._assign_payment(payment_id)
        if payment.bank is None or payment.bank.name != 'EASYPAISA':
            raise NewApiError('10212', f'Unsupported bank type: {payment.bank.name if payment.bank else ""}, supported banks: easypaisa')

        self.logger.info(
            "Request [GET] (/user/upi/%s/accounts), user: %s, name: %s",
            payment_id,
            self.current_user.id,
            self.current_user.name,
        )
        result = await EasyPaisa(self).query_bound_accounts_http(payment)
        self.logger.info(
            "Response [GET] (/user/upi/%s/accounts), user: %s, name: %s, responseData: %s",
            payment_id,
            self.current_user.id,
            self.current_user.name,
            result,
        )
        self.write(result)


class UpiAccountSelect(UpiHandler):
    @handle_errors
    async def post(self, payment_id):
        await self.authenticate_current_user()
        payment = await self._assign_payment(payment_id)
        if payment.bank is None or payment.bank.name != 'EASYPAISA':
            raise NewApiError('10212', f'Unsupported bank type: {payment.bank.name if payment.bank else ""}, supported banks: easypaisa')

        params = {'accno': self.get_body_argument('accno', default=None)}
        data = PaymentAccountSelectSchema().load(params)
        self.logger.info(
            "Request [POST] (/user/upi/%s/accounts/select), user: %s, name: %s, params: %s",
            payment_id,
            self.current_user.id,
            self.current_user.name,
            params,
        )
        result = await EasyPaisa(self).select_bound_account_http(payment, data['accno'])
        self.logger.info(
            "Response [POST] (/user/upi/%s/accounts/select), user: %s, name: %s, responseData: %s",
            payment_id,
            self.current_user.id,
            self.current_user.name,
            result,
        )
        self.write(result)


class UpiActive(UpiHandler):
    @handle_errors
    async def put(self, payment_id):
        await self.upi_active(payment_id, 'PUT')

    @handle_errors
    async def patch(self, payment_id):
        await self.upi_active(payment_id, 'PATCH')

    async def upi_active(self, payment_id, method):
        await self.authenticate_current_user()
        await self.log_user_and_ip('用户操作绑定upi')
        raw_params = self._get_params(['status', 'otp', 'upi', 'mock'])
        params = UpiActiveSchema().dump(raw_params)
        self.logger.info("Request [%s] (/user/upi/%s/active), user: %s, name: %s, params: %s",
                         method, payment_id,
                         self.current_user.id,
                         self.current_user.name,
                         params
                         )

        """标记payment本地模拟测试 10分钟"""
        if "mock" in params and "1" == params.get("mock"):
            await self.redis.set(name=f"payment_mock:{payment_id}", value="1", ex=600)

        try:
            payment = await self._assign_payment(payment_id)
        except NewApiError:
            raise NewApiError('10301')  # Payment not found 错误
            
        """
        码商 要登录 payment A 时，检查（paymentA 关联的 代收 和 代付订单中，3小时内有过期订单，返回错误提示"操作频繁等三个小时"）
        """
        count_orders_ds_within_3hours = await self._count_orders_ds_within_3hours(payment_id, payment.bank_type)
        count_orders_df_within_3hours = await self._count_orders_df_within_3hours(payment_id, payment.bank_type)
        if ((count_orders_ds_within_3hours is not None and count_orders_ds_within_3hours > 0) or
                (count_orders_df_within_3hours is not None and count_orders_df_within_3hours > 0)):
            raise NewApiError('10606')  # 操作过于频繁，3小时内已有过期订单
            
        self.logger.info("Request [%s] (/user/upi/%s/active), user: %s, name: %s, payment: %s",
                         method, payment_id,
                         self.current_user.id,
                         self.current_user.name,
                         payment
                         )

        if params['upi'] is not None:
            # 检查银行绑定的upi是否重复
            bank_upi_is_repeat = await self._check_bank_upi_is_repeat(payment_id, payment.bank_type_id, params['upi'])

            self.logger.info("Request [%s] (/user/upi/%s/active), user: %s, name: %s, bank_upi_is_repeat: %s",
                             method, payment_id,
                             self.current_user.id,
                             self.current_user.name,
                             bank_upi_is_repeat
                             )
            if bank_upi_is_repeat:
                responseData = {
                    "data": {
                        "isSuccess": False,
                        "message": f"The UPI you bound is duplicated"
                    }
                }
                self.logger.error("Response [%s] (/user/upi/%s/active), user: %s, name: %s, responseData: %s",
                                 method, payment_id,
                                 self.current_user.id,
                                 self.current_user.name,
                                 responseData
                                 )
                self.write(responseData)
                return

        service_class = BANK_SERVICES[payment.bank.name]
        service = service_class(self.db_orm, self.redis, self.redis_pub, self.logger)

        # 根据payment_id修改upi
        await self.updateUPIByPaymentId(payment_id, params['upi'])

        self.logger.info("Request [%s] (/user/upi/%s/active), updateUPIByPaymentId(), user: %s, name: %s, payment_id: %s, upi: %s",
                          method, payment_id,
                          self.current_user.id,
                          self.current_user.name,
                          payment_id,
                          params['upi']
                          )
        payment.upi = params['upi']
        responseData = None
        if service_class.LOGIN_METHOD == 'webview':
            self.logger.info("Request [%s] (/user/upi/%s/active), 准备调用 validate_webview_login_status(payment), user: %s, name: %s, payment: %s",
                             method, payment_id,
                             self.current_user.id,
                             self.current_user.name,
                             payment
                             )
            # check redis key
            await service.validate_webview_login_status(payment)
            responseData = {
                "data": {
                    "isSuccess": True,
                    "payment": UpiPaymentSchema().dump(payment),
                    "otp": False,
                    "otp_digits": 0,
                    "active_path": f"/api/v1/user/upi/{payment.id}/active",
                    "cookie_path": f"/api/v1/user/upi/{payment.id}/cookie",
                    "status": PAYMENT_STATUS[payment.status]
                }
            }
        elif service_class.LOGIN_METHOD == 'OTP':
            if params['otp']:
                self.logger.info(
                    "Request [%s] (/user/upi/%s/active), 准备调用 push_login_otp_to_redis(payment, params['otp']), user: %s, name: %s, payment: %s, otp: %s",
                    method, payment_id,
                    self.current_user.id,
                    self.current_user.name,
                    payment, params['otp']
                    )
                await service.push_login_otp_to_redis(payment, params['otp'])
                responseData = {
                    "data": {
                        "isSuccess": True,
                        "payment": UpiPaymentSchema().dump(payment),
                        "otp": False,
                        "active_path": None,
                        "cookie_path": None,
                        "status": PAYMENT_STATUS[payment.status]
                    }
                }
            else:
                otp_digits = OTP_DIGITS.get(payment.bank.name, 4)

                self.logger.info(
                    "Request [%s] (/user/upi/%s/active), 准备调用 handle_activation(payment), user: %s, name: %s, payment: %s",
                    method, payment_id,
                    self.current_user.id,
                    self.current_user.name,
                    payment
                    )

                await service.handle_activation(payment)
                responseData = {
                    "data": {
                        "isSuccess": True,
                        "payment": UpiPaymentSchema().dump(payment),
                        "otp": True,
                        "otp_digits": otp_digits,
                        "active_path": f"/api/v1/user/upi/{payment.id}/active",
                        "cookie_path": f"/api/v1/user/upi/{payment.id}/cookie",
                        "status": PAYMENT_STATUS[payment.status]
                    }
                }

        # 设置upi_active upi的缓存key
        upi_active_payment_key = f"upi_active_payment:{payment_id}"
        await self.redis.set(upi_active_payment_key, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ex=600)

        self.logger.info(
            f"Response [{method}] (/user/upi/{payment_id}/active), "
            f"user: {self.current_user.id}, "
            f"name: {self.current_user.name}, "
            f"添加缓存 key: {upi_active_payment_key}, "
            f"responseData: {responseData}"
        )
        self.write(responseData)

    """
    根据payment_id修改upi
    """
    async def updateUPIByPaymentId(self, payment_id, upi):
        if payment_id is None or upi is None:
            return
        with self.db_orm.sessionmaker() as session:
            stmt = (
                update(Payment).
                where(Payment.id == payment_id).
                values(upi=upi)
            )
            session.execute(stmt)
            session.commit()



class UpiSelling(UpiHandler):

    @handle_errors
    async def post(self):
        await self.authenticate_current_user()
        await self.validate_user_active()
        raw_params = self._get_params(['status'])
        params = UpiSellingSchema().load({'certified': raw_params['status']})
        with self.db_orm.sessionmaker() as session:
            session.execute(
                update(Payment)
                .where(Payment.user_id == self.current_user.id)
                .values(certified=CERTIFIED_STATUS[params['certified']])
            )
            session.commit()

            self.write({
                "data": {
                    "message": f"all payments are {'activated' if params['certified'] == 'active' else 'deactivated'}"
                }
            })

    @handle_errors
    async def put(self, payment_id):
        await self.upi_selling(payment_id)

    @handle_errors
    async def patch(self, payment_id):
        await self.upi_selling(payment_id)
    """
    打开或者关闭otp 接单状态
    """
    async def upi_selling(self, payment_id):
        await self.authenticate_current_user()
        await self.validate_user_active()
        raw_params = self._get_params(['status'])
        UpiSellingSchema().load({'certified': raw_params['status']})

        payment = await self._assign_payment(payment_id)

        service_class = BANK_SERVICES[payment.bank.name]
        with self.db_orm.sessionmaker() as session:
            service = service_class(self.db_orm, self.redis, self.redis_pub, self.logger)

            if raw_params['status'] == 'active' and payment.status:
                await service.selling_active(payment.id)
                self.write({
                    "data": {
                        "message": f"selling activated",
                        "status": "active"
                    }
                })
            elif raw_params['status'] == 'active' and not payment.status:
                raise ApiError(
                    'Please Active first, or waiting for payment to be active.'
                )
            elif raw_params['status'] == 'inactive':
                await service.selling_inactive(payment_id)
                self.write({
                    "data": {
                        "message": f"selling deactivated",
                        "status": "inactive"
                    }
                })
            session.commit()


class AssignUpi(UpiHandler):
    @handle_errors
    async def put(self, payment_id):
        await self.upi_assign(payment_id)

    @handle_errors
    async def patch(self, payment_id):
        await self.upi_assign(payment_id)

    async def upi_assign(self, payment_id):
        await self.authenticate_current_user()
        await self.log_user_and_ip('upi_assign')
        raw_params = self._get_params(['upi'])
        payment = await self._assign_payment(payment_id)
        raw_payment = UpiPaymentSchema().dump(payment)
        if raw_params['upi'] not in raw_payment['upi_list']:
            raise NewApiError('10301')  # Upi not found in the upi list

        with self.db_orm.sessionmaker() as session:
            stmt = (
                update(Payment).
                where(Payment.id == payment.id).
                values(upi=raw_params['upi'])
            )
            session.execute(stmt)
            session.commit()
            self.write({
                "data": {
                    "payment": UpiPaymentSchema().dump(await self._assign_payment(payment_id)),
                    "message": "Upi assigned successfully"
                }
            })


class StoreCookie(UpiHandler):
    @handle_errors
    async def post(self, payment_id):
        await self.authenticate_current_user()
        await self.validate_user_active()
        headers = self.get_argument('headers', None)
        cookie = self.get_argument('cookie', None)

        self.logger.info("----------This is Cookie---------------")
        self.logger.info(cookie)
        self.logger.info("----------End of Cookie---------------")
        payment = await self._assign_payment(payment_id)
        if payment.bank.name != 'AMAZON':
            raise NewApiError('10307')  # 银行类型不匹配，只支持AMAZON银行

        service = AmazonService(self.db_orm, self.redis, self.redis_pub, self.logger)
        service.cookie = cookie
        service.headers = headers
        await service.handle_activation(payment)

        self.write({
            "data": {
                "payment": UpiPaymentSchema().dump(payment),
                "otp": False,
                "otp_digits": 0,
                "active_path": f"/api/v1/user/upi/{payment.id}/active",
                "cookie_path": f"/api/v1/user/upi/{payment.id}/cookie",
                "status": PAYMENT_STATUS[payment.status]
            }
        })


class AbnormalPayment(UpiHandler):
    @handle_errors
    async def post(self):
        await self.authenticate_current_user()
        await self.validate_user_active()

        # 查询锁定的支付码
        locked_payments = []
        payment_ids = []

        # 查询成功率过低码，查询redis所有以 'send_orders_ds_limit_' 开头的键
        locked_payment_keys = await self.redis.keys('send_orders_ds_limit_*')
        if len(locked_payment_keys) > 0:
            for key in locked_payment_keys:
                # 提取 'payment'，去掉 'send_orders_ds_limit_' 部分
                payment_id = key.replace('send_orders_ds_limit_', '')
                payment_ids.append(payment_id)

        # 查询代收成功率低，被冻结一小时的码
        orders_ds_limit_success_rate = "orders_ds_limit_success_rate"
        redis_orders_ds_limit_success_rate_count = await self.redis.get(orders_ds_limit_success_rate)

        redis_orders_ds_limit_keys = await self.redis.keys('orders_ds_limit_*')
        for redis_orders_ds_limit in redis_orders_ds_limit_keys:
            orders_ds_list_count = await self.redis.get(redis_orders_ds_limit)

            if orders_ds_list_count and redis_orders_ds_limit_success_rate_count and int(orders_ds_list_count) < int(redis_orders_ds_limit_success_rate_count):
                payment_id = redis_orders_ds_limit.replace('orders_ds_limit_', '')
                payment_ids.append(payment_id)


        # 查询暂时锁定的码的信息
        if len(payment_ids) > 0:
            # 查询被死码
            with self.db_orm.sessionmaker() as session:
                where_clause = and_(Payment.id.in_(payment_ids))
                payments = session.query(Payment).filter(where_clause) \
                    .options(joinedload(Payment.bank)) \
                    .all()
                locked_payments = PaymentSchema(many=True).dump(payments)


        # 查询死码
        died_payments = []
        # 获取集合'payment_online_ds' 中的所有值
        payment_online_ds = await self._collection_online_payment_ids()

        # 查询被死码
        with self.db_orm.sessionmaker() as session:
            where_clause = and_(Payment.id.in_(payment_online_ds),
                                Payment.manual_status == 1 )
            payments = session.query(Payment).filter(where_clause) \
                .options(joinedload(Payment.bank)) \
                .all()
            died_payments = PaymentSchema(many=True).dump(payments)

        self.write({
            "data": {
                "locked_payments": locked_payments,
                "died_payments": died_payments,
            }
        })

"""
发送socket消息到前端partner
"""
class SendMessageToPartner(UpiHandler):
    @handle_errors
    async def post(self):
        """
        向指定通道发送消息
        """
        try:
            data = json.loads(self.request.body)
            user_id = data.get('user_id')
            message = data.get('message')

            if not user_id or not message:
                raise NewApiError('10201')  # Missing required parameters: user_id or message

        except json.JSONDecodeError:
            raise NewApiError('10901')  # Invalid JSON format

        self.logger.info(
            "Request [POST] (/websocket/send_message_to_partner), user_id: %s, message: %s",
            user_id,
            message
        )

        # 直接使用 redis 检查用户是否在线
        connection_info = await self.redis.hget(RedisKeys.REDIS_WS_CLIENTS, str(user_id))

        if not connection_info:
            response_data = {
                "data": {
                    "message": "User is not online",
                    "success": False
                }
            }
            self.logger.warning(
                "Response [POST] (/websocket/send_message_to_partner), user not online, user_id: %s",
                user_id
            )
            self.write(response_data)
            return

        # 发送消息到用户的个人通道
        channel_name = f"user_channel_{user_id}"
        num_received = await self.redis_pub.publish(
            channel_name,
            json.dumps(message)
        )

        response_data = {
            "data": {
                "message": "Message sent successfully",
                "success": True,
                "receivers": num_received
            }
        }

        self.logger.info(
            "Response [POST] (/websocket/send_message_to_partner), success, user_id: %s, receivers: %d",
            user_id,
            num_received
        )
        self.write(response_data)
class SendSmsSuccess(UpiHandler):
    @handle_errors
    async def post(self):
        params = self._get_params(['payment_id'])
        if await self.is_null(params, ['payment_id']):
            raise NewApiError('10201')  # Parameter Error

        payment_id = params['payment_id']
        self.logger.info("Request [POST] (/user/upi/send_sms_success), payment_id: %s", payment_id)

        # 检查发送短信的缓存是否存在

        with self.db_orm.sessionmaker() as session:
            _payment = session.query(Payment).options(joinedload(Payment.bank)).filter(and_(Payment.id == payment_id)).first()
            if _payment is None:
                raise NewApiError('10301')  # Payment not found

            if _payment and _payment.bank and _payment.bank.name and str(_payment.bank.name).lower() in ['maha']:
                redis_key_send_sms = f"payment_protocol_status_notify:{PaymentLoginProgress.DATA_TO_SEND_SMS.name.lower()}:{payment_id}"
                if not await self.redis.exists(redis_key_send_sms):
                    raise NewApiError('10308')  # SMS验证超时，请在30秒内完成短信验证

            key = f"send_{_payment.bank.name.lower()}_sms_success"

            push_status = await self.redis.lpush(key, payment_id)
            if not push_status:
                raise NewApiError('10902')  # Redis操作失败，系统错误

            self.write({
                "data": {
                    "message": f"send OTP success",
                    "status": "success",
                }
            })


class GrabOTP(UpiHandler):
    @handle_errors
    async def post(self):
        params = self._get_params(['bank_name', 'phone'])
        if await self.is_null(params, ['bank_name', 'phone']):
            raise NewApiError('10201')  # Parameter Error
        with self.db_orm.sessionmaker() as session:
            bank = session.query(BankType).filter_by(name=params["bank_name"]).first()
            if bank is None:
                raise NewApiError('10201')  # Bank not found by bank_name

            _payment = session.query(Payment).filter(and_(Payment.bank_type_id == bank.id,
                                                         Payment.phone == params["phone"])).first()
            if _payment is None:
                raise NewApiError('10301')  # Payment not found

            key = "login_indus_OTP_{}".format(_payment.id)
            result = await self.redis.get(key)

            if result:
                self.write({
                    "data": {
                        "message": f"grab OTP success",
                        "status": "success",
                        "OTP": result
                    }
                })
            else:
                self.write({
                    "data": {
                        "message": f"grab OTP failed",
                        "status": "failed"
                    }
                })

# 获取upi详情数据
class UpiDetail(UpiHandler):
    @handle_errors
    async def get(self):
        await self.authenticate_current_user()

        payment_id = self.get_query_argument('payment_id', None)
        with self.db_orm.sessionmaker() as session:
            where_clause = and_(Payment.user_id == self.current_user.id, Payment.id == payment_id)

            payment = session.query(Payment).filter(where_clause).first()
            if not payment:
                raise  NewApiError('10301')  # Payment not found

            raw_payment = UpiPaymentSchema().dump(payment)
        payment_with_status = await self.set_lock_status_from_redis(raw_payment)
        response_data = {
            "data": {
                "payment": payment_with_status
            }
        }
        self.write(response_data)

    async def set_lock_status_from_redis(self, payment):
        self.logger.info("[METHOD] set_lock_status_from_redis() INTO, user: %s, name: %s, payments: %s", self.current_user.id, self.current_user.name, payment)
        with self.db_orm.sessionmaker() as session:
            service_class = BANK_SERVICES[payment['bank_name']]
            service = service_class(session, self.redis, self.redis_pub, self.logger)
            payment['place_order_status'] = await self._check_place_order_status(payment['id'])
            payment['selling_order_status'] = await service.selling_order_status(payment['id'])

            payment_id = payment['id']
            # 锁定状态
            order_ttl = 0
            send_order_ttl = 0
            formatted_expire_time = ''
            redis_key = f"orders_ds_limit_{payment['id']}"
            orders_lock_status = (await self.redis.get(redis_key) is not None)
            if orders_lock_status :
                order_ttl = await self.redis.ttl(redis_key)

            redis_key = f"send_orders_ds_limit_{payment['id']}"
            send_orders_lock_status =(await self.redis.get(redis_key) is not None)
            if send_orders_lock_status :
                send_order_ttl = await self.redis.ttl(redis_key)

            ttl = (send_order_ttl if send_order_ttl > order_ttl else order_ttl)
            if ttl > 0 :
                # 当前时间
                current_time = datetime.now()
                # 计算过期时间：当前时间 + TTL秒数
                expire_time = current_time + timedelta(seconds=ttl)
                # 将过期时间转换为所需的格式: yyyy-MM-dd hh:mm:ss
                formatted_expire_time = expire_time.strftime('%Y-%m-%d %H:%M:%S')

            payment['lock_status'] = orders_lock_status or send_orders_lock_status
            payment['lock_expire_time'] = formatted_expire_time

            # 死码状态
            payment['died_status'] = payment['manual_status']

            # active状态
            payment['payment_upi_active_expire_seconds'] = (await self.redis.ttl(f"upi_active_payment:{payment['id']}"))
            payment['active_status'] = payment['payment_upi_active_expire_seconds'] > 0

            # 查询最近的10单
            limit = 10
            sql = text("""select status from orders_ds where payment_id={payment_id} and status in(4,3,-1)  order by id desc limit {limit}""".format(
                payment_id=payment_id, limit=limit))
            orders_ds_list = session.execute(sql).fetchall()
            orders_ds_list_count = 0
            for i in orders_ds_list:
                if i[0] == -1:
                    orders_ds_list_count += 1
            # 近10笔成功率
            payment['order_10_rate'] = int( float(format(1 - float(orders_ds_list_count) / float(limit), ".2f")) * 100)

            # 查单状态(bill pending)
            sql = text(
                """ select count(id) from orders_cd where  payment_id = {payment_id}""".format(payment_id=payment_id))
            bill_pending_count = session.execute(sql).fetchone()
            payment['bill_pending_count'] = bill_pending_count[0]

            # 限额状态(limit single)
            sql = text(
                """ select ds_min,ds_max from partner where id = {id} """.format(id=self.current_user.id))
            result = session.execute(sql).fetchone()
            if result is None:
                payment['limit_status'] = False
            else :
                payment['ds_min'] = str(result[0])
                payment['ds_max'] = str(result[1])

            # 查询当前payment自动支付的收款账号数量
            sql = """
            select sum(t.c) from (
                select count(code) as c from orders_df where payment_id = {payment_id} and status in (1,2,3,4,-1)
                union ALL
                select count(code) as c from orders_df_cancel where payment_id = {payment_id}
            ) as t
            """
            execute_sql = text(sql.format(payment_id=payment_id))
            number_of_automatic_payees = session.execute(execute_sql).fetchone()
            payment['number_of_automatic_payees'] = int(number_of_automatic_payees[0])
            # 配额(Allocation quota)

            # min single transcation


        self.logger.info("[METHOD] set_lock_status_from_redis() return, user: %s, name: %s, payment: %s",
                         self.current_user.id, self.current_user.name, payment)
        return payment


# 获取payment的登录进度
class LoginProgress(UpiHandler):
    @handle_errors
    async def get(self):
        await self.authenticate_current_user()
        payment_id = self.get_query_argument('payment_id', None)
        # progress = self.get_query_argument('progress', None)
        # payment_login_progress = string_to_enum(progress)
        # if PaymentLoginProgress.DATA_TO_SEND_SMS == payment_login_progress:
        #     pass
        # payment = await self._assign_payment(payment_id)

        response_data = {
            PaymentLoginProgress.DATA_TO_SEND_SMS.name.lower(): None,
            PaymentLoginProgress.STATUS_OF_SENDING_OTP.name.lower(): None,
            PaymentLoginProgress.SEND_SMS_CHECK.name.lower(): None,
            PaymentLoginProgress.STATUS_OF_VERIFY_OTP.name.lower(): None,
            PaymentLoginProgress.STATUS_OF_VERIFY_MPIN.name.lower(): None,
            PaymentLoginProgress.STATUS_OF_LOGIN.name.lower(): None
        }

        try:
            # 获取发送短信的数据
            redis_key_send_sms = f"payment_protocol_status_notify:{PaymentLoginProgress.DATA_TO_SEND_SMS.name.lower()}:{payment_id}"
            redis_key_send_sms_str = await self.redis.get(redis_key_send_sms)
            if StringUtils.is_valid_json(redis_key_send_sms_str):
                send_sms = json.loads(redis_key_send_sms_str)
                response_data[PaymentLoginProgress.DATA_TO_SEND_SMS.name.lower()] = send_sms

            # 短信发送的检查结果
            redis_key_send_sms_check = f"payment_protocol_status_notify:{PaymentLoginProgress.SEND_SMS_CHECK.name.lower()}:{payment_id}"
            redis_key_send_sms_check_str = await self.redis.get(redis_key_send_sms_check)
            if StringUtils.is_valid_json(redis_key_send_sms_check_str):
                send_sms_check = json.loads(redis_key_send_sms_check_str)
                response_data[PaymentLoginProgress.SEND_SMS_CHECK.name.lower()] = send_sms_check

            # 获取OTP验证码的发送状态
            redis_key_status_of_sending_otp = f"payment_protocol_status_notify:{PaymentLoginProgress.STATUS_OF_SENDING_OTP.name.lower()}:{payment_id}"
            redis_key_status_of_sending_otp_str = await self.redis.get(redis_key_status_of_sending_otp)
            if StringUtils.is_valid_json(redis_key_status_of_sending_otp_str):
                status_of_sending_otp = json.loads(redis_key_status_of_sending_otp_str)
                response_data[PaymentLoginProgress.STATUS_OF_SENDING_OTP.name.lower()] = status_of_sending_otp

            # 协议检查客户端输入OTP的结果
            redis_key_status_of_verify_otp = f"payment_protocol_status_notify:{PaymentLoginProgress.STATUS_OF_VERIFY_OTP.name.lower()}:{payment_id}"
            redis_key_status_of_verify_otp_str = await self.redis.get(redis_key_status_of_verify_otp)
            if StringUtils.is_valid_json(redis_key_status_of_verify_otp_str):
                status_of_verify_otp = json.loads(redis_key_status_of_verify_otp_str)
                response_data[PaymentLoginProgress.STATUS_OF_VERIFY_OTP.name.lower()] = status_of_verify_otp

            # 协议检查客户端输入MPIN的结果
            redis_key_status_of_verify_mpin = f"payment_protocol_status_notify:{PaymentLoginProgress.STATUS_OF_VERIFY_MPIN.name.lower()}:{payment_id}"
            redis_key_status_of_verify_mpin_str = await self.redis.get(redis_key_status_of_verify_mpin)
            if StringUtils.is_valid_json(redis_key_status_of_verify_mpin_str):
                status_of_verify_mpin = json.loads(redis_key_status_of_verify_mpin_str)
                response_data[PaymentLoginProgress.STATUS_OF_VERIFY_MPIN.name.lower()] = status_of_verify_mpin

            # 获取登录状态
            redis_key_payment_login_status = f"payment_protocol_status_notify:{PaymentLoginProgress.STATUS_OF_LOGIN.name.lower()}:{payment_id}"
            redis_key_payment_login_status_str = await self.redis.get(redis_key_payment_login_status)
            if redis_key_payment_login_status_str:
                try:
                    redis_key_payment_login_status_dict = json.loads(redis_key_payment_login_status_str)
                    response_data[PaymentLoginProgress.STATUS_OF_LOGIN.name.lower()] = redis_key_payment_login_status_dict.get("is_success")
                except json.JSONDecodeError:
                    self.logger.error(f"Invalid JSON in STATUS_OF_LOGIN for payment_id: {payment_id}")
                    raise NewApiError('10901')  # System error
        except json.JSONDecodeError:
            self.logger.error(f"Invalid JSON in redis data for payment_id: {payment_id}")
            raise NewApiError('10901')  # System error
        except Exception as e:
            self.logger.error(f"Error getting login progress: {str(e)}")
            raise NewApiError('10901')  # System error

        self.logger.info(f"[GET] /user/upi/login_progress, payment_id: {payment_id}, response_data: {json.dumps(response_data)}")
        self.write(response_data)
