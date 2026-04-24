import asyncio
import os
import time
import random
import json
from urllib.parse import parse_qs
from datetime import datetime, timedelta
from decimal import Decimal

from aiomysql import DictCursor

from application.lakshmi_api.base import BaseHandler, ApiError
from application.lakshmi_api.error_handler import handle_errors

from application.lakshmi_api.models.usdt_deposit_order import UsdtDepositOrder
from application.lakshmi_api.models.sys_info import SysInfo
from application.lakshmi_api.models.user import User
from application.lakshmi_api.models.balance_record import BalanceRecord
from application.lakshmi_api.schema.partner_schema import PartnerSchema
from application.lakshmi_api.schema.usdt_deposit_order_schema import UsdtDepositOrderSchema, SingleUsdtOrderSchema
from application.lakshmi_api.services.pagination_service import PaginationService

from application.lakshmi_api.services.copy_button_service import CopyButtonService

from sqlalchemy import and_, desc, update
from config import get_config

conf = get_config()
INCOMPLETE_ORDER_STATUS = [0, 1]
VALID_STATUSES = [-1, 0, 1, 2]
HAS_COPY_ATTRIBUTES = {'serial_number': True, 'usdt_amount': True, 'exchange_rate': False, 'currency_amount': False,
                       'block_chain': False, 'bonus_rate': False, 'bonus': False, 'address': True, 'created_at': False,
                       'total_amount': False}


class Orders(BaseHandler):
    @handle_errors
    async def post(self):
        await self.authenticate_current_user()
        await self._check_user_has_existing_order()

        # 检查是否是系统锁定代收代付对账
        is_locked = await self.check_dsdf_lock()
        if is_locked:
            raise ApiError(", please try again later.")
        
        # 判斷開關為開/金額限制範圍/地址有無
        params = self._get_params(['block_chain', 'usdt_amount'])
        usdt_order = UsdtDepositOrderSchema().load(params)
        usdt_amount = Decimal(usdt_order["usdt_amount"])
        with self.db_orm.sessionmaker() as session:
            sys_info = session.query(SysInfo).first()
            usdt_amount_limit = sys_info.usdt_amount_limit if sys_info else None
            usdt_exchange_status = sys_info.usdt_exchange_status if sys_info else None
            usdt_received_address = sys_info.usdt_received_address if sys_info else None
            if usdt_amount_limit and usdt_amount > usdt_amount_limit:
                raise ValueError("The 'usdt_amount' exceeds the limit, limit: {usdt_amount_limit} U".format(usdt_amount_limit=usdt_amount_limit))
            if usdt_exchange_status != 1:
                raise ValueError("Invalid usdt_exchange_status.")
            if usdt_received_address is None or usdt_received_address.strip() == "":
                raise ValueError("No usdt_received_address exists.")
        # 使用者輸入的金額加上鎖 以防止相同金額綁定地址
        cycle = 0
        while True:
            amount_lock = f"usdt_amount_lock_{usdt_order['usdt_amount']}"
            if await self.redis.setnx(amount_lock, 1):
                await self.redis.expire(amount_lock, 10)
                break
            if cycle >= 20:
                self.logger.warning(f"{usdt_order['usdt_amount']} is locked.{self.current_user.id}")
                raise ApiError(f"try other usdt_amount instead of {usdt_order['usdt_amount']}")
            time.sleep(0.2)
            cycle += 1
        # 找到資料庫裡沒被金額綁定的地址
        addresses = ([address.strip() for address in sys_info.usdt_received_address.split(',') if address.strip()])
        random.shuffle(addresses)
        selected_address = None
        for address in addresses:
            unique_key = 'usdt_' + address + '_' + str(usdt_order['usdt_amount'])
            if not await self.redis.exists(unique_key):
                selected_address = address
                break
        if not selected_address:
            await self.redis.delete(amount_lock)
            raise ValueError("No address available, please wait or try other amount.")

        # 訂單寫入資料庫/返回給前端
        try:
            with self.db_orm.sessionmaker() as session:
                new_order = UsdtDepositOrder(
                    user_id=self.current_user.id,
                    usdt_amount=Decimal(usdt_order["usdt_amount"]),
                    block_chain=usdt_order["block_chain"],
                    status=1,
                    address=selected_address
                )
                session.add(new_order)
                session.commit()
                data = UsdtDepositOrderSchema().dump(new_order)
            self.write({
                "usdt_order": data,
            })
            unique_key = 'usdt_' + selected_address + '_' + str(usdt_order['usdt_amount'])
            await self.redis.set(unique_key, data['serial_number'], 60 * 40)
            await self.redis.delete(amount_lock)
        except Exception as e:
            await self.redis.delete(amount_lock)
            self.logger.warning(e)
            raise ValueError("There was an error while writing to the database.")

    def _get_params(self, keys):
        params = {}
        for key in keys:
            params[key] = self.get_body_argument(key, default=None)
        return params

    async def _check_user_has_existing_order(self):
        forty_minutes_ago = datetime.now() - timedelta(minutes=40)
        with self.db_orm.sessionmaker() as session:
            usdt_order_count = session.query(UsdtDepositOrder).filter(
                and_(UsdtDepositOrder.user_id == self.current_user.id, UsdtDepositOrder.status.in_(INCOMPLETE_ORDER_STATUS)), UsdtDepositOrder.created_at >= forty_minutes_ago).count()
        # 最多一次性5次提单
        if usdt_order_count >6:
            raise ApiError('You have incomplete {count} orders.'.format(count=usdt_order_count))

    @handle_errors
    async def get(self):
        await self.authenticate_current_user()

        time_frame = self.set_value_to_integer("time_frame", 7)
        date_from = (datetime.now() - timedelta(days=time_frame))
        where_clause = and_(UsdtDepositOrder.updated_at >= date_from,
                            UsdtDepositOrder.user_id == self.current_user.id)
        with self.db_orm.sessionmaker() as session:
            total_count = session.query(UsdtDepositOrder).filter(where_clause).count()
            pagination_service = PaginationService(self.request.path, self.request)
            offset, limit, pagination_data = await pagination_service.get_pagination_data(total_count)

            usdt_orders = session.query(UsdtDepositOrder).filter(where_clause) \
                .order_by(desc(UsdtDepositOrder.id)) \
                .offset(offset) \
                .limit(limit) \
                .all()

        usdt_order_schema = UsdtDepositOrderSchema(many=True)
        self.write({
            "data": {
                "user": PartnerSchema().dump(self.current_user),
                "orders": usdt_order_schema.dump(usdt_orders)
            },
            "pagination": pagination_data
        })


class EditOrder(BaseHandler):
    @handle_errors
    async def get(self, serial_number):
        await self.authenticate_current_user()
        where_clause = and_(UsdtDepositOrder.serial_number == serial_number,
                            UsdtDepositOrder.user_id == self.current_user.id)
        with self.db_orm.sessionmaker() as session:
            usdt_order = session.query(UsdtDepositOrder).filter(where_clause).first()
            if usdt_order is None:
                raise ApiError("order not found")
            elif usdt_order.receipt_image:
                raise ApiError("order already have receipt image")
            elif usdt_order.status == 2:
                raise ApiError("order already paid")

        filtered_data = SingleUsdtOrderSchema().dump(usdt_order)
        formatted_data = CopyButtonService(HAS_COPY_ATTRIBUTES).process(filtered_data)
        self.write({"data": {"usdt_order": formatted_data}})


class Order(BaseHandler):
    @handle_errors
    async def put(self, serial_number):
        await self.upload_receipt(serial_number)

    @handle_errors
    async def patch(self, serial_number):
        await self.upload_receipt(serial_number)

    async def upload_receipt(self, serial_number):
        await self.authenticate_current_user()
        with self.db_orm.sessionmaker() as session:
            order = session.query(UsdtDepositOrder).filter(and_(UsdtDepositOrder.serial_number == serial_number,
                                                                UsdtDepositOrder.user_id == self.current_user.id,
                                                                UsdtDepositOrder.status.in_(INCOMPLETE_ORDER_STATUS),
                                                                UsdtDepositOrder.receipt_image == 0)).one_or_none()

            files = self.request.files
            self.validate_request(files, order)
            receipt_image = files['receipt'][0]
            file_extension = receipt_image.filename.split('.')[-1].lower()
            if not file_extension in ['jpg', 'jpeg', 'png', 'bmp', 'tif', 'tiff']:
                raise ApiError('invalid file format')

            image_path = f"static/upload/{order.serial_number}.jpg"
            os.makedirs(os.path.dirname(image_path), exist_ok=True)
            with open(image_path, 'wb') as f:
                f.write(receipt_image['body'])
            if await self._lock_row_by_redis(order.serial_number):
                order.receipt_image = True
                session.commit()
                await self._unlock_row_by_redis(order.serial_number)
            self.write({"data": {"message": "success"}})

    @staticmethod
    def validate_request(files, order):
        if not files or len(files.get('receipt', [])) != 1:
            raise ApiError("invalid file upload")
        if not order:
            raise ApiError("order not found")
        if order.receipt_image:
            raise ApiError("order already has receipt_image")

    async def _lock_row_by_redis(self, usdt_order_serial_number):
        busy_key = f"grab_usdt_{usdt_order_serial_number}"

        for lock_acquire_loop in range(25):
            if await self.redis.setnx(busy_key, 1):
                await self.redis.expire(busy_key, 10)
                return True
            if self.redis.exists(busy_key):
                await asyncio.sleep(0.2)
        # If the code execution reaches this point, it means it has tried 25 times and still cannot acquire the lock.
        # At this time, it should warn the user.
        self.logger.warning(f"deposit order ID:{usdt_order_serial_number} Do not operate frequently")
        raise ApiError(f"deposit order ID:{usdt_order_serial_number}. Please retry later.")

    async def _unlock_row_by_redis(self, usdt_order_serial_number):
        busy_key = f"grab_usdt_{usdt_order_serial_number}"
        await self.redis.delete(busy_key)


class Callback(BaseHandler):
    async def post(self):
        # 只接受白名单ip访问
        ip = await self.get_ip()
        if not ip in ["127.0.0.1", "::1"]:
            return self.write({'success': False, 'message': '{ip} ip not permitted'.format(ip=ip)})

        order_data = {k: self.get_argument(k) for k in self.request.arguments}
        # order_data = self.urlencoded_to_json(self.request.body.decode("utf-8"))
        self.logger.info('usdt callback:' + json.dumps(order_data))
        if await self.is_null(order_data, ['serial_number', 'paid_at', 'transaction_id']):
            return self.write({'success': False, 'message': 'params error'})

        # 使用锁，5s使用自旋锁，防止并发回调
        count_circle = 0
        while True:
            busy_key = 'grab_usdt_{code}'.format(code=order_data['serial_number'])
            if await self.redis.setnx(busy_key, 1):
                await self.redis.expire(busy_key, 10)
                break
            if count_circle >= 25:
                self.logger.warning('usdt callback code:{} Do not operate frequently'.format(order_data['serial_number']))
                return self.write({'success': False, 'message': 'Do not operate frequently'})
            time.sleep(0.2)
            count_circle = count_circle + 1

        try:
            with self.db_orm.sessionmaker() as session:
                order = session.query(UsdtDepositOrder).filter_by(serial_number=order_data['serial_number']).first()
                if not order:
                    await self.redis.delete(busy_key)
                    return self.write({'success': False, 'message': 'order not found'})
                if not order.status == 1:
                    await self.redis.delete(busy_key)
                    return self.write({'success': True, 'message': 'order has been filled'})
                if order.status == 1:
                    order.status = 2
                    order.txid = order_data['transaction_id']
                    original_balance = order.user.balance
                    stmt = update(User).where(User.id == order.user.id).values(
                        balance=User.balance + order.total_amount)
                    session.execute(stmt)
                    revised_balance = original_balance + order.total_amount
                    user = session.query(User).filter(User.id == order.user.id).one()
                    new_balance_record = BalanceRecord(
                        user_id=user.id,
                        serial_number=order.serial_number,
                        change_before=original_balance,
                        amount=order.total_amount,
                        change_after=revised_balance,
                        record_type=7,
                        user_type=0,
                        remark=f"{order.usdt_amount}*{order.exchange_rate}*{1 + order.bonus_rate}={order.total_amount}"
                    )
                    session.add(new_balance_record)
                    order.paid_at = order_data['paid_at']

                    amount = order.total_amount
                    partner_id = order.user_id

                    # 只有外部码商参与优惠
                    if user.genre == 1:
                        # 代付优惠
                        disprice = Decimal(0)
                        sys_info = session.query(SysInfo).one()
                        range_df = sys_info.range_usdt_df
                        if range_df:
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
                            if not await self.change_balance(session, 'partner', partner_id, disprice, order.serial_number, 10):
                                session.rollback()
                                return self.write({'success': False, 'message': 'Failed to add partner balance'})
                session.commit()
                await self.redis.delete(busy_key)
        except Exception as e:
            await self.redis.delete(busy_key)
            self.logger.error('usdt callbac error : {}'.format(json.dumps(order_data)))
            self.logger.error(e)
            return self.write({'success': False, 'message': 'usdt callbac error'})
        self.logger.info('usdt callback code:{} successful'.format(order_data['serial_number']))
        self.write({"success": True})

    @staticmethod
    def urlencoded_to_json(encoded_data_str):
        parsed = parse_qs(encoded_data_str)
        return {k: v[0] for k, v in parsed.items() if v}


class RevokeOrder(BaseHandler):
    @handle_errors
    async def put(self, serial_number):
        await self.revoke_order(serial_number)

    @handle_errors
    async def patch(self, serial_number):
        await self.revoke_order(serial_number)

    async def revoke_order(self, serial_number):
        # 暫時不使用
        raise ApiError("not working")
        await self.authenticate_current_user()
        with self.db_orm.sessionmaker() as session:
            order = session.query(UsdtDepositOrder).filter(and_(UsdtDepositOrder.serial_number == serial_number,
                                                                UsdtDepositOrder.user_id == self.current_user.id,
                                                                UsdtDepositOrder.status.in_(
                                                                    INCOMPLETE_ORDER_STATUS))).first()
            if order is None:
                raise ApiError("order does not exist")
            order.status = -1
            session.commit()
            data = UsdtDepositOrderSchema().dump(order)

        self.write({
            "usdt_order": data,
        })
