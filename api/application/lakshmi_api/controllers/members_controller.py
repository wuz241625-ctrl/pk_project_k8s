import os
import random
from decimal import Decimal

import bcrypt
import math
from sqlalchemy.sql.functions import current_user

from application.lakshmi_api.base import BaseHandler, ApiError, BearerTokenError
from application.lakshmi_api.models import *
from application.lakshmi_api.schema.partner_schema import MemberSchema, PartnerSchema
from application.lakshmi_api.services.pagination_service import PaginationService
from application.lakshmi_api.services.partner_tree_service import PartnerTreeService
from application.lakshmi_api.error_handler import handle_errors
from application.lakshmi_api.schema.transfer_order_schema import TransferOrderSchema
from sqlalchemy import and_, text, desc
from datetime import datetime, timedelta, time

from application.lakshmi_api.services.redis_service import RedisService
from application.lakshmi_api.services.sms_service import SmsService

DATE_OPTIONS = {
    '1D': datetime.combine(datetime.now() - timedelta(days=1), datetime.min.time()),
    '3D': datetime.combine(datetime.now() - timedelta(days=3), datetime.min.time()),
    '7D': datetime.combine(datetime.now() - timedelta(days=7), datetime.min.time()),
    '1M': datetime.combine(datetime.now() - timedelta(days=30), datetime.min.time()),
    '3M': datetime.combine(datetime.now() - timedelta(days=90), datetime.min.time()),
}
BEGINNING_OF_DAY = datetime.combine(datetime.now(), time.min)
END_OF_DAY = datetime.combine(datetime.now(), time.max)
TIMEZONE = '+05:30'


class MemberHandler(BaseHandler):
    def _get_params(self, keys):
        params = {}
        for key in keys:
            params[key] = self.get_body_argument(key, default=None)
        return params

    async def _get_member_summary(self, parent_id):
        start_date = DATE_OPTIONS['1D']
        date_option = self.get_query_argument('date_options', default=None)
        if date_option in DATE_OPTIONS.keys():
            start_date = DATE_OPTIONS[date_option]

        partner_service = PartnerTreeService()
        partners = await partner_service.self_and_descendants(parent_id)
        partner_ids = [partner.id for partner in partners]
        partner_not_include_self_ids = [partner.id for partner in partners if partner.id != parent_id]
        deposit_where_clause = and_(DepositOrder.order_placed_at >= start_date,
                                    DepositOrder.status == 4,
                                    DepositOrder.user_id.in_(partner_ids))

        withdraw_where_clause = and_(WithdrawOrder.order_placed_at >= start_date,
                                     WithdrawOrder.status == 4,
                                     WithdrawOrder.user_id.in_(partner_ids))

        with self.db_orm.sessionmaker() as session:
            deposit_orders = session.query(DepositOrder).filter(deposit_where_clause).all()
            withdraw_orders = session.query(WithdrawOrder).filter(withdraw_where_clause).all()
            new_members = session.query(User).filter(and_(User.id.in_(partner_not_include_self_ids),
                                                          User.created_at >= start_date)).all()
        member_summary = {'total_deposit': sum(order.amount for order in deposit_orders),
                          'total_withdraw': sum(order.amount for order in withdraw_orders),
                          'orders_count': len(deposit_orders) + len(withdraw_orders),
                          'new_member_count': len(new_members)}
        return member_summary

    async def _personal_summary(self, parent_id):
        start_date = DATE_OPTIONS['1D']
        date_option = self.get_query_argument('date_options', default=None)
        if date_option in DATE_OPTIONS.keys():
            start_date = DATE_OPTIONS[date_option]
        
        withdraw_where_clause = and_(
            WithdrawOrder.order_placed_at >= start_date,
            WithdrawOrder.status == 4,
            WithdrawOrder.user_id == parent_id
        )

        deposit_where_clause = and_(
            DepositOrder.order_placed_at >= start_date,
            DepositOrder.status == 4,
            DepositOrder.user_id == parent_id
        )

        with self.db_orm.sessionmaker() as session:
            deposit_orders = session.query(DepositOrder).filter(deposit_where_clause).all()
            withdraw_orders = session.query(WithdrawOrder).filter(withdraw_where_clause).all()
            deposit_orders_count = len(deposit_orders)
            withdraw_orders_count = len(withdraw_orders)

        personal_summary = {
            "personal_buy_orders": sum(order.amount for order in deposit_orders),
            "personal_sell_orders": sum(order.amount for order in withdraw_orders),
            "personal_orders_count": deposit_orders_count + withdraw_orders_count
        }
        return personal_summary
    
    async def _get_recent_profit(self, parent_id):
        today_start_at = datetime.combine(datetime.now(), datetime.min.time())
        today_end_at = datetime.combine(datetime.now(), datetime.max.time())
        yesterday_start_at = datetime.combine(datetime.now() - timedelta(days=1), datetime.min.time())
        yesterday_end_at = datetime.combine(datetime.now() - timedelta(days=1), datetime.max.time())

        with self.db_orm.sessionmaker() as session:
            deposit_orders_today = session.query(DepositOrder).filter(
                DepositOrder.order_placed_at >= today_start_at,
                DepositOrder.order_placed_at <= today_end_at,
                DepositOrder.status == 4,
                DepositOrder.user_id == parent_id).all()
            deposit_orders_yesterday = session.query(DepositOrder).filter(
                DepositOrder.order_placed_at >= yesterday_start_at,
                DepositOrder.order_placed_at <= yesterday_end_at,
                DepositOrder.status == 4,
                DepositOrder.user_id == parent_id).all()
            withdraw_orders_today = session.query(WithdrawOrder).filter(
                WithdrawOrder.order_placed_at >= today_start_at,
                WithdrawOrder.order_placed_at <= today_end_at,
                WithdrawOrder.status == 4,
                WithdrawOrder.user_id == parent_id).all()
            withdraw_orders_yesterday = session.query(WithdrawOrder).filter(
                WithdrawOrder.order_placed_at >= yesterday_start_at,
                WithdrawOrder.order_placed_at <= yesterday_end_at,
                WithdrawOrder.status == 4,
                WithdrawOrder.user_id == parent_id).all()
        yesterday_profit = sum(order.benefit for order in deposit_orders_yesterday) + sum(
            order.benefit for order in withdraw_orders_yesterday)
        today_profit = sum(order.benefit for order in deposit_orders_today) + sum(
            order.benefit for order in withdraw_orders_today)
        profit_percentage = ((today_profit - yesterday_profit) / max(yesterday_profit, 1)) * 100
        recent_profit = {
            "yesterday_profit": yesterday_profit,
            "today_profit": today_profit,
            "percentage": profit_percentage
        }
        return recent_profit

    async def _get_parent(self):
        """
        this method for check the user belongs to the partner want to query
        by default, this app will use self.current_user.id
        but use also can click the check his descendant status
        """
        parent_id = self.get_query_argument('parent_id', default=None)
        if parent_id is None or parent_id == '' or (parent_id is not None and int(parent_id) == 0):
            return self.current_user.id
        # only return the member in the tree belong to current_user
        with self.db_orm.sessionmaker() as session:
            descendant = session.query(PartnerTree).filter(
                PartnerTree.parent == self.current_user.id,
                PartnerTree.child == parent_id).one_or_none()
        if descendant:
            return descendant.child

        raise ApiError('Member Not found')

    async def _get_members(self, parent_id, options):
        """
        this method need to double-check if it has the risk to sql injection
        """
        condition_query = ''
        limit_query = ''

        if 'name' in options:
            condition_query += f"AND partner.name LIKE '{options['name']}'"
        if 'limit_offset' in options:
            limit_query += f"LIMIT {options['limit_offset']}"
        if 'limit' in options:
            limit_query += f"LIMIT {options['limit']}"
        # 20250930 partner_tree.distance != 0 AND  delete
        query = f'''
            SELECT partner.id, partner.name
            FROM partner_tree
                LEFT JOIN partner ON partner_tree.child = partner.id
            WHERE partner_tree.parent = :parent_id {condition_query}
            {limit_query}
        '''
        with self.db_orm.sessionmaker() as session:
            return session.execute(text(query), {'parent_id': parent_id}).fetchall()

    @staticmethod
    def _verify_payment_password_bcrypt(password, hashed_password):
        if not bcrypt.checkpw(password.encode('utf8'), hashed_password.encode('utf8')):
            raise ApiError('Payment Password Incorrect')

    async def _send_otp(self, phone):
        sms_service = SmsService()
        redis_service = RedisService()
        cooldown_milliseconds = await redis_service.show_sms_otp_cooldown_in_millisecond(phone)
        if cooldown_milliseconds > 0:
            cooldown_seconds = math.ceil(cooldown_milliseconds / 1000)
            raise ApiError(f"Please try it again after {cooldown_seconds} seconds")
        if await sms_service.send_itniotech_sms(phone):
            await redis_service.set_sms_otp_cooldown(phone)
            if os.environ.get('RUN_ENV') == 'DEV':
                return {
                    "data": {
                        "otp_dev": sms_service.code,
                    }
                }
            else:
                return {
                    "data": {}
                }
        else:
            raise ApiError('Fail to sent OTP, please try again')

    async def _verify_otp(self, partner):
        service = RedisService()
        valid_otp = await service.validate_sms_otp(partner['cellphone'], partner['otp'], False)

        if not valid_otp:
            raise ApiError('OTP is not valid')

class Summary(MemberHandler):
    @handle_errors
    async def get(self):
        await self.authenticate_current_user()
        parent_id = await self._get_parent()
        member_summary = await self._get_member_summary(parent_id)
        personal_summary = await self._personal_summary(parent_id)
        if not any(member_summary):
            raise ApiError('No record found')
        # it should list all child belongs this current user
        current_user_members = await self._get_members(self.current_user.id, {})
        with self.db_orm.sessionmaker() as session:
            members_count = session.query(PartnerTree).filter(
                and_(PartnerTree.parent == parent_id, PartnerTree.distance != 0)).count()

        profit = await self._get_recent_profit(parent_id)
        self.write({
            'data': {
                'yesterday_profit': round(float(profit['yesterday_profit']), 2),
                'today_profit': round(float(profit['today_profit']), 2),
                'percentage': round(float(profit['percentage']), 2),
                'members': MemberSchema(many=True).dump(current_user_members),
                'members_count': members_count,
                'new_members_count': member_summary['new_member_count'],
                'total_sell_orders': float(member_summary['total_withdraw']),
                'total_buy_orders': float(member_summary['total_deposit']),
                'total_orders_count': float(member_summary['orders_count']),
                'personal_sell_orders': float(personal_summary['personal_sell_orders']),
                'personal_buy_orders': float(personal_summary['personal_buy_orders']),
                'personal_orders_count': float(personal_summary['personal_orders_count'])
            },
            'date_options': list(DATE_OPTIONS.keys())
        })


class FindMember(MemberHandler):
    @handle_errors
    async def get(self):
        await self.authenticate_current_user()
        parent_id = await self._get_parent()
        name = self.request.arguments.get('name')[0].decode() if 'name' in self.request.arguments else None

        options = {}
        if name:
            options = {'name': f'%{name}%'}

        members = await self._get_members(parent_id, options)
        pagination_service = PaginationService(self.request.path, self.request)
        offset, limit, pagination_data = await pagination_service.get_pagination_data(len(members))
        options['limit_offset'] = f'{offset}, 99999'

        members = await self._get_members(parent_id, options)

        self.write({
            'data': MemberSchema().dump(members, many=True),
        })


class BalanceTransfer(MemberHandler):
    async def prepare(self):
        await super().prepare()
        await self.check_ip_access_frequency(20, 10)

    @handle_errors
    async def post(self):
        await self.authenticate_current_user()
        await self.log_user_and_ip('用户操作转账')
        is_pass = await self.check_user_access_frequency(100, 60 * 30)
        if not is_pass:
            self.set_status(403)
            return self.write("Can't continue to operate")
        await self.validate_user_active()
        await self.verify_upi_requirements()
        params = self._get_params(['to_user_id', 'amount', 'payment_password'])

        # check here first, we also need to check when update
        if self.current_user.balance < Decimal(params['amount']):
            raise ApiError("Balance cannot be more than the current balance.")
        # verify payment password
        self._verify_payment_password_bcrypt(params['payment_password'], self.current_user.hash_trade)

        otp = self.get_body_argument('otp', None)

        if otp is not None:
            # verify OTP
            params['cellphone']=self.current_user.cellphone
            params['otp']=otp
            await self._verify_otp(params)
            with self.db_orm.sessionmaker() as session:
                target_user = session.query(User).filter(User.id == int(params['to_user_id'])).first()
                # check if target_user is None
                if target_user is None:
                    self.logger.warning(f"余额转账，接受码商 {params['to_user_id']} 不存在")
                    raise ApiError("Member with this ID does not exist.")
                three_hours_ago = datetime.now() - timedelta(hours=3)
                where_clause = and_(WithdrawOrder.user_id == self.current_user.id,
                                    WithdrawOrder.created_at >= three_hours_ago)
                orderDsOne = session.query(WithdrawOrder).filter(where_clause).first()
                # check if target_user is None
                if orderDsOne is not None:
                    self.logger.warning(f"码商 {self.current_user.id} 3个小时内有接单记录{orderDsOne.serial_number}无法转账")
                    raise ApiError("transfer after 3 hours of sell ends")
                # create transfer order
                serial_number = 'Z' + ''.join(str(datetime.now().timestamp()).split('.')) + str(random.randint(1000, 9999))
                remark = str(self.current_user.id) + "码商操作，转账至" + str(params['to_user_id'])
                new_transfer_order = TransferOrder(
                    serial_number=serial_number,
                    user_id=self.current_user.id,
                    to_user_id=params['to_user_id'],
                    amount=Decimal(params['amount']),
                    status=2,
                    remark=remark
                )
                self.logger.info(f"新增转帐订单：{str(new_transfer_order)}")
                session.add(new_transfer_order)

                # check user object again
                current_user = session.query(User).filter(User.id == self.current_user.id).first()
                original_balance = current_user.balance
                # revised balance, it will update database when session.commit
                current_user.balance -= Decimal(params['amount'])
                revised_balance = current_user.balance
                self.logger.info(f"更改金额码商ID{current_user.id},金额从{original_balance}改为{revised_balance}")
                if current_user.balance < 0:
                    session.rollback()
                    raise ApiError('Transfer Amount cannot be more than the current balance.')

                # create balance change record(deduct)
                new_balance_record = BalanceRecord(
                    serial_number=serial_number,
                    change_before=original_balance,
                    amount=-Decimal(params['amount']),
                    change_after=revised_balance,
                    record_type=8,
                    user_id=self.current_user.id,
                    user_type=0,
                    remark=f"转账至：{str(params['to_user_id'])}"
                )
                self.logger.info(f"新增流水：-{str(new_balance_record)} to {current_user.id}")
                session.add(new_balance_record)

                original_balance = target_user.balance
                # revised balance, it will update database when session.commit
                target_user.balance += Decimal(params['amount'])
                revised_balance = target_user.balance
                # create balance change record(deduct)
                new_balance_record = BalanceRecord(
                    serial_number=serial_number,
                    change_before=original_balance,
                    amount=Decimal(params['amount']),
                    change_after=revised_balance,
                    record_type=8,
                    user_id=target_user.id,
                    user_type=0,
                    remark=f"收款來自：{str(self.current_user.id)}"
                )
                self.logger.info(f"新增流水：{str(new_balance_record)} to {target_user.id}")
                session.add(new_balance_record)

                session.commit()
            with self.db_orm.sessionmaker() as session:
                new_transfer_order = session.query(TransferOrder).filter_by(serial_number=serial_number).one()
                self.write({
                    'data': TransferOrderSchema().dump(new_transfer_order)
                })
        else:
            await self._send_otp(self.current_user.cellphone)
            self.write(
                {
                    "data": {
                        "otp": True,
                        "otp_digits": 4,
                        "transfer_path": "/api/v1/members/balance_transfer",
                        "method": 'POST'
                    }
                }
            )

    async def verify_upi_requirements(self):
        with self.db_orm.sessionmaker() as session:
            payments = session.query(Payment).filter(Payment.user_id == self.current_user.id, Payment.upi.isnot(None)).all()
            upi_count = len(payments)
        if upi_count < 2:
            raise ApiError('Please active more APIs')

class TransferOrders(MemberHandler):
    @handle_errors
    async def get(self):
        await self.authenticate_current_user()
        await self.validate_user_active()
        with (self.db_orm.sessionmaker() as session):
            where_clause = and_(TransferOrder.user_id == self.current_user.id,
                                TransferOrder.status == 2)
            total_count = session.query(TransferOrder).filter(where_clause).count()
            pagination_service = PaginationService(self.request.path, self.request)
            offset, limit, pagination_data = await pagination_service.get_pagination_data(total_count)
            transfer_orders = session.query(TransferOrder) \
                .filter(where_clause) \
                .order_by(desc(TransferOrder.id)) \
                .all()
            transfer_order_schema = TransferOrderSchema(many=True)
            self.write({
                "data": {
                    "user": PartnerSchema().dump(self.current_user),
                    "transfer_orders": transfer_order_schema.dump(transfer_orders)
                },
                "pagination": pagination_data
            })
