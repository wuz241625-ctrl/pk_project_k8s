import asyncio
import json
import os
import logging

import simplejson
from sqlalchemy import not_

from application.lakshmi_api.base import BaseHandler, ApiError, BearerTokenError
from application.lakshmi_api.base_websocket import WebsocketBaseHandler
from application.lakshmi_api.schema.deposit_order_schema import OrderDataSchema, SingleDepositOrderSchema, DepositOrderSchema, NewOrderSchema, OrderStatus

from application.lakshmi_api.schema.partner_schema import PartnerSchema
from application.lakshmi_api.services.copy_button_service import CopyButtonService
from application.lakshmi_api.services.pagination_service import PaginationService
from application.lakshmi_api.services.query_filter_service import QueryFilterService
from application.lakshmi_api.error_handler import handle_errors
from datetime import datetime, timedelta
from application.lakshmi_api.models.deposit_order import DepositOrder
from application.lakshmi_api.models.deposit_order_cancel import DepositOrderCancel
from application.lakshmi_api.models.sys_info import SysInfo
from application.lakshmi_api.models.payment import Payment
from sqlalchemy import and_, desc
from sqlalchemy.orm import joinedload

from application.utils import CustomJsonEncoder, HashUtils

HAS_COPY_ATTRIBUTES = {'serial_number': True, 'Amount': True, 'IFSC': True, 'Name': True,
                       'Account': True, 'Bank': True, 'benefit': False, 'created_at': False}
INVALID_ORDER_STATUS = [
    -2,  # UNKNOWN
    -1,  # REVOKED
    0,  # PENDING
]
VALID_STATUSES = [1, 2, 3, 4]
INCOMPLETE_ORDER_STATUS = [1, 2]


class OrderHandler(BaseHandler):
    def _get_params(self, keys):
        params = {}
        for key in keys:
            params[key] = self.get_body_argument(key, default=None)
        return params

    async def _authenticate_current_user(self):
        current_user = await self.async_get_current_user()
        if current_user is None:
            raise BearerTokenError
        else:
            return current_user

    async def _assign_payment(self, payment_id, current_user):
        with self.db_orm.sessionmaker() as session:
            payment = session.query(Payment).filter(and_(Payment.id == payment_id,
                                                         Payment.user_id == current_user.id)).first()

        if not payment:
            raise ApiError('payment not found')
        else:
            return payment


class Orders(OrderHandler):
    @handle_errors
    async def get(self):
        await self.authenticate_current_user()
        min_value = self.get_query_argument('min', None)
        max_value = self.get_query_argument('max', None)
        max_value = self.override_max_amount_if_outer_partner(max_value)
        pending_condition = DepositOrder.status == 0
        amount_range_condition = self.amount_range_condition(min_value, max_value)
        where_clause = and_(pending_condition, amount_range_condition)
        conditions = [amount_range_condition]
        conditions.append(pending_condition)
        conditions.append(DepositOrder.ifsc.notlike('AIR%'))
        # 获取当前时间
        current_time = datetime.now()
        # 计算7天前的时间
        time_7_days_ago = current_time - timedelta(days=7)
        time_create_condition = DepositOrder.created_at >= time_7_days_ago
        # 增加条件：查询7天内创建的数据
        conditions.append(and_(time_create_condition))

        # 查询 SysInfo 表的第一条记录（假设 merchant_ids 字段存在于此表中）
        # 直接获取 session 实例
        session = self.db_orm.sessionmaker()
        sys_info = session.query(SysInfo).first()
        # 检查 sys_info.merchant_ids 是否非空且非 None
        if sys_info.merchant_ids is not None and sys_info.merchant_ids.strip():
            # 如果 sys_info.merchant_ids 非空且不为 None，按逗号分割并构建查询条件
            merchant_ids = sys_info.merchant_ids.split(',')
            merchant_id_condition = not_(DepositOrder.merchant_id.in_(merchant_ids))
            conditions.append(merchant_id_condition)

        # 如果是外部码商 (genre == 1)，添加额外的 parent_id 条件
        if self.current_user.genre == 1:
            # 根据你的需求，添加 parent_id 必须为 NULL 的条件
            # conditions.append(DepositOrder.parent_id.is_(None))
            conditions.append(DepositOrder.parent_id == "")

        where_clause = and_(*conditions)
        with self.db_orm.sessionmaker() as session:
            total_count = session.query(DepositOrder).filter(where_clause).count()
            pagination_service = PaginationService(self.request.path, self.request)
            offset, limit, pagination_data = await pagination_service.get_pagination_data(total_count)

            deposit_orders = session.query(DepositOrder).filter(where_clause) \
                .offset(offset) \
                .limit(limit) \
                .all()
            incomplete_order = session.query(DepositOrder).options(joinedload(DepositOrder.payment).joinedload(Payment.bank)).filter(
                and_(
                    DepositOrder.user_id == self.current_user.id,
                    DepositOrder.status.in_(INCOMPLETE_ORDER_STATUS)
                )
            ).first()
            sys_info = session.query(SysInfo).first()
            usdt_exchange_rate = float(sys_info.usdt_exchange_rate)
            usdt_exchange_status = sys_info.usdt_exchange_status
            usdt_exchange_bonus_rate = float(sys_info.usdt_exchange_bonus_rate * 100)

            orders = OrderDataSchema(many=True)
            service = QueryFilterService()
            filters = service.filter_order_amounts()
            data_dict = {
                "data": {
                    "user": PartnerSchema().dump(self.current_user),
                    "deposit_orders": orders.dump(deposit_orders),
                    # TODO: use LakshmiApiSettingSchema
                    # TODO: if false , rate and bonus should be None
                    "usdt": {
                        "exchange_rate": usdt_exchange_rate,
                        "exchange_status": usdt_exchange_status,
                        "exchange_bonus_rate": usdt_exchange_bonus_rate,
                        "blockchain": [
                            "TRC20"
                        ],
                        "place_order_path": "/api/v1/usdt/orders",
                    }
                },
                "pagination": pagination_data,
                "filters": filters
            }
            if incomplete_order is not None:
                data_dict['data']["incomplete_order"] = OrderDataSchema().dump(incomplete_order)

            self.write(data_dict)

    def override_max_amount_if_outer_partner(self, max_value):
        try:
            max_value = int(max_value)
        except ValueError:
            max_value = None
        
        if self.current_user.genre == 1 and max_value is not None and max_value >= 20000:
            self.logger.info(f"修改外部码商{self.current_user.id}查询 max amount >= 20000")
            max_value = 19999
        else:
            max_value
        return max_value

    @staticmethod
    def amount_range_condition(min_value=None, max_value=None):
        conditions = []
        if min_value is not None and max_value is not None:
            if int(max_value) > int(min_value):
                conditions.append(DepositOrder.amount >= int(min_value))
                conditions.append(DepositOrder.amount <= int(max_value))
            else:
                raise ApiError('Maximum value should be greater than minimum value')

        elif min_value is not None:
            conditions.append(DepositOrder.amount >= int(min_value))

        elif max_value is not None:
            conditions.append(DepositOrder.amount <= int(max_value))

        return and_(*conditions)

class OrdersDf(OrderHandler):
    @handle_errors
    async def get(self):
        await self.authenticate_current_user()
        payment_id = self.get_query_argument('payment_id', None)
        if payment_id is None or payment_id == '':
            raise ApiError('payment_id is required')
        with (self.db_orm.sessionmaker() as session):
            # 查询 DepositOrder
            deposit_order_query = session.query(DepositOrder).filter(
                and_(DepositOrder.payment_id == payment_id)
            ).order_by(desc(DepositOrder.created_at))

            # 查询 DepositOrderCancel
            deposit_order_cancel_query = session.query(DepositOrderCancel).filter(
                and_(DepositOrderCancel.payment_id == payment_id, DepositOrderCancel.status == OrderStatus.REVOKED.value)
            ).order_by(desc(DepositOrderCancel.created_at))

            # 合并两个查询结果
            combined_query = deposit_order_query.union_all(deposit_order_cancel_query)

            # 获取总记录数
            total_count = session.query(combined_query.subquery()).count()

            # 分页
            pagination_service = PaginationService(self.request.path, self.request)

            offset, limit, pagination_data = await pagination_service.get_pagination_data(total_count)

            combined_orders = session.query(combined_query.subquery()) \
                .offset(offset) \
                .limit(limit) \
                .all()


            row_data = [row._asdict() for row in combined_orders]
            data = json.loads(json.dumps(row_data, cls=CustomJsonEncoder))

            result_data = []
            for item in data:
                payment_id = item.get("orders_df_payment_id")
                payment = session.query(Payment).options(joinedload(Payment.bank)).filter(Payment.id==payment_id).first()

                status = OrderStatus(item.get("orders_df_status")).name

                if OrderStatus.REVOKED.name == status:
                    time_revoked = item.get("orders_df_time_updated")
                else:
                    time_revoked = ""

                item_new = {
                    "code": item.get("orders_df_code"),
                    "amount": item.get("orders_df_amount"),
                    "status": status,
                    "payment_id": item.get("orders_df_payment_id"),
                    "upi": payment.upi,
                    "bank_name": payment.bank.name,
                    "sys_remark": item.get("orders_df_sys_remark", ""),
                    "time_create": item.get("orders_df_time_create", ""),
                    "time_revoked": time_revoked,
                }
                result_data.append(item_new)

            data_dict = {
                "data": result_data,
                "pagination": pagination_data,
            }

            self.write(data_dict)

    @staticmethod
    def amount_range_condition(min_value=None, max_value=None):
        conditions = []
        if min_value is not None and max_value is not None:
            if int(max_value) > int(min_value):
                conditions.append(DepositOrder.amount >= int(min_value))
                conditions.append(DepositOrder.amount <= int(max_value))
            else:
                raise ApiError('Maximum value should be greater than minimum value')

        elif min_value is not None:
            conditions.append(DepositOrder.amount >= int(min_value))

        elif max_value is not None:
            conditions.append(DepositOrder.amount <= int(max_value))

        return and_(*conditions)


class EditOrder(OrderHandler):
    """
    代付接单后调用
    """
    @handle_errors
    async def get(self, serial_number):
        await self.authenticate_current_user()
        where_clause = and_(DepositOrder.serial_number == serial_number,
                            DepositOrder.user_id == self.current_user.id)
        with self.db_orm.sessionmaker() as session:
            deposit_order = session.query(DepositOrder).options(
                joinedload(DepositOrder.payment).joinedload(Payment.bank)).filter(where_clause).first()
            if deposit_order is None:
                raise ApiError("order not found")
            elif deposit_order.payment_img == 1:
                raise ApiError("order already have payment image")

        filtered_data = SingleDepositOrderSchema().dump(deposit_order)
        formatted_data = CopyButtonService(HAS_COPY_ATTRIBUTES).process(filtered_data)
        # formatted_data['payment_bank_name'] = deposit_order.payment.bank.name
        self.write({"data": {"deposit_order": formatted_data}})


class Order(OrderHandler):
    @handle_errors
    async def put(self, serial_number):
        await self.upload_payment(serial_number)

    @handle_errors
    async def patch(self, serial_number):
        await self.upload_payment(serial_number)

    async def upload_payment(self, serial_number):
        await self.authenticate_current_user()
        if await self._lock_row_by_redis(serial_number):
            with self.db_orm.sessionmaker() as session:
                # valid utr format
                utr = self.get_body_argument('utr', default=None)
                # allow None in utr
                if utr and not (utr.isnumeric() and len(utr) == 12):
                    raise ApiError("UTR is not valid, it must be a 12 digit number.")

                order = session.query(DepositOrder).filter(and_(DepositOrder.serial_number == serial_number,
                                                                DepositOrder.user_id == self.current_user.id,
                                                                DepositOrder.status.in_(VALID_STATUSES))).one_or_none()

                files = self.request.files
                self.validate_request(files, order)
                payment_image = files['receipt'][0]
                file_extension = payment_image.filename.split('.')[-1].lower()
                if not file_extension in ['jpg', 'jpeg', 'png', 'bmp', 'tif', 'tiff']:
                    raise ApiError('invalid file format')

                image_path = f"static/upload/{order.serial_number}.jpg"
                os.makedirs(os.path.dirname(image_path), exist_ok=True)
                with open(image_path, 'wb') as f:
                    f.write(payment_image['body'])

                if order.status == 1:
                    order.status = 2

                order.payment_img = 1
                order.utr = utr
                session.commit()
                await self._unlock_row_by_redis(order.serial_number)
            self.write({"data": {"message": "success"}})

    @staticmethod
    def validate_request(files, order):
        if not files or len(files.get('receipt', [])) != 1:
            raise ApiError("invalid file upload")
        if not order:
            raise ApiError("order not found")
        if order.payment_img == 1:
            raise ApiError("order already has payment_image")

    async def _lock_row_by_redis(self, deposit_order_serial_number):
        busy_key = f"grab_df_{deposit_order_serial_number}"

        for lock_acquire_loop in range(25):
            if await self.redis.setnx(busy_key, 1):
                await self.redis.expire(busy_key, 10)
                return True
            if self.redis.exists(busy_key):
                await asyncio.sleep(0.2)
        # If the code execution reaches this point, it means it has tried 25 times and still cannot acquire the lock.
        # At this time, it should warn the user.
        self.logger.warning(f"deposit order ID:{deposit_order_serial_number} Do not operate frequently")
        raise ApiError(f"deposit order ID:{deposit_order_serial_number}. Please retry later.")

    async def _unlock_row_by_redis(self, deposit_order_serial_number):
        busy_key = f"grab_df_{deposit_order_serial_number}"
        await self.redis.delete(busy_key)

    """
    代付接单
    """
    @handle_errors
    async def post(self, serial_number):
        await self.authenticate_current_user()

        is_locked = await self.check_dsdf_lock()
        if is_locked:
            raise ApiError("Place order is locked, please try again later.")
        
        raw_params = self._get_params(['payment_id'])
        if 'payment_id' in raw_params and raw_params['payment_id']:
            params = NewOrderSchema().load(raw_params)
            await self._check_partner_has_existing_order()
            payment = await self._assign_payment(params['payment_id'], self.current_user)

            if await self._place_order_with_lock(serial_number, payment, self.current_user):
                self.write({
                    "message": "Place order success",
                    "redirect_path": f"/api/v1/orders/{serial_number}/edit"
                })
        else:
            await self.upload_payment(serial_number)

    async def _place_order_with_lock(self, serial_number, payment, current_user):        
        if await self._lock_row_by_redis(serial_number):
            try:
                with self.db_orm.sessionmaker() as session:
                    deposit_order = session.query(DepositOrder).filter(and_(DepositOrder.serial_number == serial_number,
                                                                            DepositOrder.status == 0)).one_or_none()
                    if deposit_order is None:
                        raise ApiError('Order not found')
                    # 如果是外部码商 (genre == 1)，添加额外的 parent_id 条件
                    if self.current_user.genre == 1 and deposit_order.parent_id!='':
                        # 根据你的需求，添加 parent_id 必须为 NULL 的条件
                        raise ApiError('No right place Order')
                    
                    # 临时措施：外部码商代付订单金额不能超过20000
                    if self.current_user.genre == 1 and deposit_order.amount >= 20000:
                        raise ApiError('outer partner order amount cannot exceed 20000')

                    deposit_order.status = 1
                    deposit_order.order_placed_at = datetime.now()
                    deposit_order.user_id = current_user.id
                    deposit_order.payment_id = payment.id
                    session.commit()

                    await self.save_order_to_redis_cache(deposit_order, payment)
                    await self._unlock_row_by_redis(serial_number)

                    return True
            except Exception as error:
                await self._unlock_row_by_redis(serial_number)
                self.logger.warning("代付抢单错误:{error},code:{code}".format(error=str(error), code=serial_number))
                raise ApiError('Place order failed, please contact customer service support')

    async def _verify_order_available(self, serial_number):
        with self.db_orm.sessionmaker() as session:
            deposit_order = session.query(DepositOrder).filter(and_(DepositOrder.serial_number == serial_number,
                                                                    DepositOrder.status == 0)).one_or_none()
        if deposit_order:
            return deposit_order
        else:
            raise ApiError('Order not found')

    async def _check_partner_has_existing_order(self):
        with self.db_orm.sessionmaker() as session:
            deposit_order = session.query(DepositOrder).filter(and_(DepositOrder.user_id == self.current_user.id,
                                                                    DepositOrder.status.in_(
                                                                        INCOMPLETE_ORDER_STATUS))).first()

        if deposit_order:
            raise ApiError('You have incomplete order.')

    """
    保存要支付的订单到缓存。
    历史专用钱包协议已退役，当前不再写旧协议缓存。
    """
    async def save_order_to_redis_cache(self, order: DepositOrder, payment: Payment):
        return


class DepositOrders(OrderHandler):
    @handle_errors
    async def get(self):
        await self.authenticate_current_user()

        time_frame = self.set_value_to_integer("time_frame", 7)
        date_from = (datetime.now() - timedelta(days=time_frame))
        if self.current_user.genre == 1:# 如果是外部码商不展示 parent_id!=''的数据
            where_clause = and_(DepositOrder.updated_at >= date_from,
                                DepositOrder.status.in_(VALID_STATUSES),
                                DepositOrder.user_id == self.current_user.id
                                # 新增条件：parent_id 必须为 NULL
                                # DepositOrder.parent_id.is_(None)
                                # DepositOrder.parent_id == ""
                                )
        else:
            where_clause = and_(DepositOrder.updated_at >= date_from,
                                DepositOrder.status.in_(VALID_STATUSES),
                                DepositOrder.user_id == self.current_user.id)
        with self.db_orm.sessionmaker() as session:
            total_count = session.query(DepositOrder).filter(where_clause).count()
            pagination_service = PaginationService(self.request.path, self.request)
            offset, limit, pagination_data = await pagination_service.get_pagination_data(total_count)

            user_deposit_orders = session.query(DepositOrder).filter(where_clause) \
                .options(joinedload(DepositOrder.payment).joinedload(Payment.bank)) \
                .order_by(desc(DepositOrder.id)) \
                .offset(offset) \
                .limit(limit) \
                .all()

        deposit_order_schema = DepositOrderSchema(many=True)
        self.write({
            "data": {
                "user": PartnerSchema().dump(self.current_user),
                "orders": deposit_order_schema.dump(user_deposit_orders)
            },
            "pagination": pagination_data
        })

# 查询代付订单的详情
class OrdersDFDetail(WebsocketBaseHandler):

    @handle_errors
    async def get(self):
        code = self.get_query_argument('code', None)
        self.logger.info(f"request /websocket/orders_df, code: {code}")
        result = {
            "is_success": False,
            "data": None
        }
        try:
            with self.db_orm.sessionmaker() as session:
                order_df = session.query(DepositOrder).filter(and_(DepositOrder.serial_number == code)).first()
                result["is_success"] = True
                if order_df:
                    result["data"] = order_df.to_dict()
                    result["data"]["code"] = order_df.serial_number
                    result["data"]["time_create"] = order_df.created_at
                    result["data"]["time_accept"] = order_df.order_placed_at
                    result["data"]["time_payed"] = order_df.paid_at
                    result["data"]["time_success"] = order_df.success_at
                    result["data"]["time_updated"] = order_df.updated_at
                    result["data"]["partner_id"] = order_df.user_id
                    result["data"]["realpay"] = order_df.real_pay
                    result["data"]["payment_id"] = order_df.payment_id
                    result["data"]["earn_partner_self"] = order_df.benefit
                    result["data"]["otherpay"] = order_df.other_pay
                    data_str = json.dumps(result["data"], cls=CustomJsonEncoder)
                    result["data"] = json.loads(data_str)
        except Exception as error:
            error_message = f"Query <orders_df> failed, please contact customer service support. orders_df.code = {code}, error: {error}"
            self.logger.warning(f"error_message: {error_message}")
            result["error_message"] = error_message
        finally:
            self.write(result)
