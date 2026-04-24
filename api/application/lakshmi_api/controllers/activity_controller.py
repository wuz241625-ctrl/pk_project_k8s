import random
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from venv import create

from sqlalchemy import and_, update, text

from application.lakshmi_api.base import BaseHandler, ApiError
from application.lakshmi_api.error_handler import handle_errors
from application.lakshmi_api.models import User, Payment
from application.lakshmi_api.models.prize_earn_log import PrizeEarnLog
from application.lakshmi_api.models.prize_lottery_chance import PrizeLotteryChance
from application.lakshmi_api.models.prize_lottery_chance_log import PrizeLotteryChanceLog
from application.lakshmi_api.models.prize_pool import PrizePool
from application.lakshmi_api.models.prize_pool_log import PrizePoolLog
from application.lakshmi_api.models.prize_setting import PrizeSetting
from application.lakshmi_api.models.prize_setting_detail import PrizeSettingDetail
from application.lakshmi_api.schema.prize_schema import PrizeSettingSchema, PrizeEarnLogSchema, PrizeSettingDetailSchema


# 获取活动列表
class PrizeSettings(BaseHandler):
    @handle_errors
    async def get(self):
        with self.db_orm.sessionmaker() as session:
            now = datetime.now()
            # 查询 活动有效期内 、 开启 的抽奖活动  默认不展示满减满赠活动
            prize_settings = session.query(PrizeSetting).filter(
                and_(PrizeSetting.status == 1, PrizeSetting.is_app_show == 1,
                     PrizeSetting.begin_at <= now, PrizeSetting.end_at > now)).all()

            self.write({
                "data": {
                    "prize_settings": PrizeSettingSchema(many=True).dump(prize_settings)
                }
            })


# 获取活动列表
class PrizeSettingsDetails(BaseHandler):
    @handle_errors
    async def get(self):
        prize_id = self.get_query_argument('prize_id')
        prize_type = self.get_query_argument('prize_type')
        with self.db_orm.sessionmaker() as session:
            now = datetime.now()
            if not prize_id:
                raise ApiError('params is error')

            conditions = [PrizeSettingDetail.status == 1, PrizeSettingDetail.prize_id == prize_id]

            if prize_type:
                conditions.append(PrizeSettingDetail.prize_type == prize_type)

            where_clause = and_(*conditions)
            # 查询
            prize_setting_details = session.query(PrizeSettingDetail).filter(where_clause).all()

            self.write({
                "data": {
                    "prize_setting_details": PrizeSettingDetailSchema(many=True).dump(prize_setting_details)
                }
            })


# 获取抽奖活动信息
class LotteryInfo(BaseHandler):
    @handle_errors
    async def get(self):
        # 获取登录信息
        token = await self.get_bearer_token
        with self.db_orm.sessionmaker() as session:
            self.current_user = session.query(User).filter_by(authentication_token=token).first()

        with self.db_orm.sessionmaker() as session:
            now = datetime.now()
            # 查询 活动有效期内 、 开启 的抽奖活动
            prize_setting = session.query(PrizeSetting).filter(
                and_(PrizeSetting.status == 1, PrizeSetting.type == 0, PrizeSetting.begin_at <= now,
                     PrizeSetting.end_at > now)).first()

            if prize_setting is None:
                raise ApiError('Content not found')

            # 查询 抽奖活动奖池金额
            prize_pool = session.query(PrizePool).filter(PrizePool.id == 1).first()

            # 查询 用户抽奖活动次数， 未登录显示为0 ，登录后 查询用户抽奖次数
            chance_num = 0
            if token is not None and self.current_user is not None:
                user_chance = session.query(PrizeLotteryChance).filter(
                    PrizeLotteryChance.user_id == self.current_user.id).with_for_update().first()
                if user_chance:
                    chance_num = user_chance.chance_num

            self.write({
                "data": {
                    "prize_setting": PrizeSettingSchema().dump(prize_setting),
                    "pool_amount": str(prize_pool.pool_amount),
                    "user_chance_num": chance_num
                }
            })


# 抽奖中奖记录查询
class LotteryPrizeLogs(BaseHandler):
    @handle_errors
    async def get(self):
        prize_id = self.get_query_argument('prize_id')
        user_id = self.get_query_argument('user_id')

        with self.db_orm.sessionmaker() as session:
            now = datetime.now()
            # 查询 活动有效期内 、 开启 的抽奖活动
            prize_logs = session.query(PrizeEarnLog).filter(
                and_(PrizeEarnLog.prize_id == prize_id), PrizeEarnLog.user_id == user_id).all()
            prize_earn_log_schema = PrizeEarnLogSchema(many=True)
            self.write({
                "data": prize_earn_log_schema.dump(prize_logs)
            })


# 抽奖方法
class DrawLottery(BaseHandler):
    @handle_errors
    async def post(self):
        await self.authenticate_current_user()
        busy_key = 'prize_pool_lock'
        with self.db_orm.sessionmaker() as session:
            now = datetime.now()
            # 查询用户信息
            user = session.query(User).filter_by(id=self.current_user.id).first()

            last_draw_time = await self.redis.get(f'user_last_draw_time_{self.current_user.id}')
            if last_draw_time :
                raise ApiError("User can only draw once every 2 seconds, please try again later.")

            await self.redis.set(f'user_last_draw_time_{self.current_user.id}', datetime.now().timestamp(), 2)

            # 查询 活动有效期内 、 开启 的抽奖活动
            prize_setting = session.query(PrizeSetting).filter(
                and_(PrizeSetting.status == 1, PrizeSetting.type == 0, PrizeSetting.begin_at <= now,
                     PrizeSetting.end_at > now)).first()
            if prize_setting is None:
                raise ApiError('prize setting not found')
            prize_id = prize_setting.id

            # 计算中奖项
            prize_setting_detail = await self.draw_lottery(session, prize_id)

            try:
                # 扣减抽奖机会
                user_chance = session.query(PrizeLotteryChance).filter(
                    PrizeLotteryChance.user_id == self.current_user.id).with_for_update().first()

                if not user_chance:
                    raise ApiError("User have no chance to draw prizes")

                _before_num = user_chance.chance_num

                if _before_num <= 0 :
                    raise ApiError("User have no chance to draw prizes")

                # 扣减抽奖机会
                user_chance.chance_num -= 1

                # 记录抽奖机会变动
                chance_log = PrizeLotteryChanceLog(
                    user_id=self.current_user.id,
                    prize_id=prize_id,
                    before_num=_before_num,
                    num=-1,
                    after_num=_before_num - 1,
                    remark="参与抽奖，机会次数-1",
                    created_at=datetime.now()
                )
                session.add(chance_log)

                # 中奖项唯一码
                key = await  self.get_lottery_key(session, prize_setting_detail)

                if key == 'lucky':
                    # 幸运奖 优先派单限时2个小时，后自动返回普通派单
                    await self.send_lucky_prize(self, session, user)

                    remark = '参与抽奖，抽中幸运奖, 支付码优先派单2个小时'
                    amount = 0

                else:
                    # 处理奖励金额的逻辑

                    # 锁定奖池
                    # 获取锁，10秒内锁定
                    if not await self.redis.setnx(busy_key, 1):
                        return False
                    await self.redis.expire(busy_key, 10)
                    # 扣减奖池
                    prize_pool = session.query(PrizePool).filter(PrizePool.id == 1).with_for_update().first()

                    _before_amount = prize_pool.pool_amount

                    # 计算中奖金额
                    if prize_setting_detail.prize_type == 1:
                        amount = prize_setting_detail.money
                        # 判断固定中奖金额是否超出奖池金额， 若超出奖池余额，则改为中幸运奖
                        if prize_pool.pool_amount < amount:
                            # 幸运奖
                            await self.send_lucky_prize(self, session, user)
                            remark = '参与抽奖，抽中幸运奖, 支付码优先派单2个小时'
                            amount = 0
                            key = 'lucky'
                        else:
                            remark = '参与抽奖，抽中{title}, 奖励金额{amount}'.format(title=prize_setting_detail.title,
                                                                                     amount=amount)
                    elif prize_setting_detail.prize_type == 2:
                        # 奖励类型为：奖池比例
                        amount = prize_pool.pool_amount * prize_setting_detail.money

                        # amount 四舍五入，保留4位小数
                        amount = amount.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)

                        remark = '参与抽奖，抽中{title}, 奖池金额为{before_amount}，奖励奖池金额的{ratio}%, 奖励金额{amount}'.format(
                            title=prize_setting_detail.title, before_amount=_before_amount,
                            ratio=prize_setting_detail.money * 100, amount=amount)
                    else:
                        # 幸运奖已处理，这里无需处理
                        raise ApiError('prize setting error')

                    change_after = prize_pool.pool_amount - amount
                    # 扣减奖池
                    prize_pool.pool_amount = change_after

                    # 更改码商余额
                    code = await self.create_code("JC")
                    if not await self.change_balance(session, 'partner', user.id, amount, code, 10):
                        session.rollback()
                        return self.write({'success': False, 'message': 'Failed to add partner balance'})

                    # 记录奖池变动
                    prize_pool_log = PrizePoolLog(
                        code=code,
                        record_type=2,
                        change_before=_before_amount,
                        amount=amount,
                        change_after=change_after,
                        user_type=0,
                        user_id=user.id,
                        remark=remark,
                        created_at=datetime.now()
                    )
                    session.add(prize_pool_log)

                # 增加中奖记录
                prize_earn_log = PrizeEarnLog(
                    user_id=user.id,
                    user_name=user.name,
                    prize_id=prize_id,
                    prize_detail_id=prize_setting_detail.id,
                    prize_title=prize_setting.title,
                    money=amount,
                    remark=remark,
                    created_at=datetime.now()
                )
                session.add(prize_earn_log)

                session.commit()

                self.write(
                    {
                        "data": {
                            "message": "success",
                            "amount": str(amount),
                            "key": key
                        }
                    }
                )
            except Exception as e:
                session.rollback()
                self.logger.error(e)
                self.write(
                    {
                        "data": {
                            "message": "Failed to draw lottery"
                        }
                    }
                )
            finally:
                session.close()
                # 执行完成删除锁
                await self.redis.delete(busy_key)

    # 计算中奖奖项
    @staticmethod
    async def draw_lottery(session, prize_id):
        # 查询抽奖活动设置
        prize_setting_details = session.query(PrizeSettingDetail).filter(
            and_(PrizeSettingDetail.status == 1, PrizeSettingDetail.prize_id == prize_id)).all()

        if not prize_setting_details:
            raise ApiError('prize setting detail not found')

        # 计算总抽奖概率
        total_probability = sum(detail.ratio for detail in prize_setting_details)

        # 累积概率范围
        cumulative_probabilities = []
        cumulative = 0
        for detail in prize_setting_details:
            cumulative += Decimal(detail.ratio)
            cumulative_probabilities.append((cumulative, detail))

        # 生成随机数并选择奖品
        rand = random.uniform(0, float(total_probability))  # 随机数在 0 到 抽奖总概率 之间
        for cumulative, detail in cumulative_probabilities:
            if rand <= cumulative:
                return detail

    # 获取 中奖项的唯一key
    @staticmethod
    async def get_lottery_key(session, prize_setting_detail):
        if prize_setting_detail.prize_type == 1:
            # 固定奖励，以奖励金额为唯一key
            return str(int(prize_setting_detail.money))
        elif prize_setting_detail.prize_type == 2:
            # 若是奖池比例奖励
            # 查询奖励的排名
            sql = """
                SELECT COUNT(1) as count FROM prize_setting_detail 
                WHERE prize_id = :prize_id  AND money > :money AND status = 1 
            """
            result = session.execute(text(sql), {"prize_id": prize_setting_detail.prize_id,
                                                 "money": prize_setting_detail.money}).first()
            if result.count == 0:
                return 'grand'
            elif result.count == 1:
                return 'first'
            elif result.count == 2:
                return 'second'
            else:
                return 'third'
        else:
            # 返回幸运奖
            return "lucky"

    # 发放幸运奖
    @staticmethod
    async def send_lucky_prize(self, session, user):
        # 查询 码商下 所有payment 并 更改为优先派单
        payments = session.query(Payment).filter(Payment.user_id == user.id).all()
        # 执行更新
        stmt = update(Payment).where(Payment.user_id == user.id).values(priority_collection=1)
        session.execute(stmt)

        for payment in payments:
            _key = "priority_collection_{payment_id}".format(payment_id=payment.id)
            await self.redis.set(_key, 1, 2 * 60 * 60)
        pass

    # 创建编码
    @staticmethod
    async def create_code(PRE='R'):
        return PRE + ''.join(str(datetime.now().timestamp()).split('.')) + str(random.randint(1000, 9999))
