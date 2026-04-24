import json
import logging
from datetime import datetime, timedelta
from typing import Any, Coroutine, List

from sqlalchemy import and_, text, select, update, insert
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import joinedload

from application.lakshmi_api.base import BaseHandler, ApiError
from application.lakshmi_api.error_handler import handle_errors
from application.lakshmi_api.models import *
from application.lakshmi_api.models.payment import Payment
from application.lakshmi_api.models.prize_partner_beginner_tutorial_task_progress import \
    PrizePartnerBeginnerTutorialTaskProgress
from application.lakshmi_api.models.prize_setting import PrizeSetting
from application.lakshmi_api.models.prize_setting_partner_beginner_tutorial_task import \
    PrizeSettingPartnerBeginnerTutorialTask
from application.lakshmi_api.schema.partner_schema import PrizeSettingPartnerBeginnerTutorialTaskSchema


class PartnerHandler(BaseHandler):
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

            raise ApiError('Bank not found')


"""
处理新手任务
"""


class BeginnerTaskProgressHandler(PartnerHandler):
    # 创建记录
    async def createTaskProgress(self, prize_id: int, partner_id: int, time_register: datetime):
        with self.db_orm.sessionmaker() as session:
            stmt = insert(PrizePartnerBeginnerTutorialTaskProgress).values(
                PrizePartnerBeginnerTutorialTaskProgress.prize_id == prize_id,
                PrizePartnerBeginnerTutorialTaskProgress.partner_id == partner_id,
                PrizePartnerBeginnerTutorialTaskProgress.is_finished == 0,
                PrizePartnerBeginnerTutorialTaskProgress.is_awarded == 0,
                PrizePartnerBeginnerTutorialTaskProgress.prize_amount == 0,
                PrizePartnerBeginnerTutorialTaskProgress.time_register == time_register,
            ).returning(PrizePartnerBeginnerTutorialTaskProgress.id)
            self.logger.info(f"stmt: {stmt}")
            result = session.execute(stmt)
            return result

    # 更新记录（观看新手视频）
    async def updateTaskProgress(self, taskProgress: PrizePartnerBeginnerTutorialTaskProgress):
        with self.db_orm.sessionmaker() as session:
            stmt = update(PrizePartnerBeginnerTutorialTaskProgress).where(and_(
                PrizePartnerBeginnerTutorialTaskProgress.id == taskProgress.id,
            )).values(PrizePartnerBeginnerTutorialTaskProgress)
            self.logger.info(f"stmt: {stmt}")
            result = session.execute(stmt)
            return result

    # 查询一个进行中的新手活动
    async def get_activity(self) -> PrizeSetting:
        current_time = datetime.now()
        with self.db_orm.sessionmaker() as session:
            prizeSetting = session.query(PrizeSetting).filter(and_(
                PrizeSetting.type == 3,
                PrizeSetting.status == 1
            )).first()
            if prizeSetting is None:
                self.logger.warning(f"未查询到进行中的新手活动")
                return None
            return prizeSetting

    # 查询新手活动任务列表
    async def queryTaskList(self, prizeSettingId: int, taskStatusEnable: int) -> List[PrizeSettingPartnerBeginnerTutorialTask]:
        with self.db_orm.sessionmaker() as session:
            filters = []
            filters.append(PrizeSettingPartnerBeginnerTutorialTask.prize_id == prizeSettingId)
            if taskStatusEnable is not None:
                filters.append(PrizeSettingPartnerBeginnerTutorialTask.status_enable == taskStatusEnable)

            query = session.query(PrizeSettingPartnerBeginnerTutorialTask).filter(*filters)
            # 执行查询
            taskList = query.all()
            if taskList is None:
                self.logger.warning(f"未查询到新手活动的任务列表。prizeSettingId: {prizeSettingId}")
                return None
            return taskList

    # 查询指定码商的新手任务完成进度
    async def getTaskProgress(self, partnerId: int, prizeSettingId: int) -> PrizePartnerBeginnerTutorialTaskProgress:
        with self.db_orm.sessionmaker() as session:
            stmt = select(PrizePartnerBeginnerTutorialTaskProgress).where(
                and_(
                    PrizePartnerBeginnerTutorialTaskProgress.partner_id == partnerId,
                    PrizePartnerBeginnerTutorialTaskProgress.prize_id == prizeSettingId
                )
            )
            query = session.scalars(stmt)
            try:
                taskProgress = query.one()
            except NoResultFound:
                self.logger.warning(f"未查询到新手活动的任务进度。partnerId: {partnerId}, prizeSettingId: {prizeSettingId}")
                taskProgress = None

            return taskProgress

"""
查看指定新手任务进度
1、查询进行中的新手活动
2、查询当前用户的完成进度
3、返回任务列表及参数进度
"""
class getBeginnerTaskProgress(BeginnerTaskProgressHandler):
    @handle_errors
    async def get(self):
        await self.authenticate_current_user()
        # 接收参数（是否启用;0=是,1=否）
        task_status_enable = self.get_query_argument('task_status_enable')
        self.logger.info("Request [POST] (/partner/get_beginner_task_progress), current_user: %s", self.current_user)
        # 查询一个进行中的新手任务活动
        prizeSetting = await self.get_activity()
        # 没有活动时，直接返回
        if not prizeSetting:
            self.write({
                "data": {
                    "message": f"ok",
                    "status": "success"
                }
            })
            return
        current_time = datetime.now()
        self.logger.info(f"current_user: {self.current_user}, current_time: {current_time}, prizeSetting: {prizeSetting}")
        taskList = await self.queryTaskList(prizeSettingId = prizeSetting.id, taskStatusEnable = task_status_enable)
        if not taskList:
            self.write({
                "data": {
                    "message": f"ok",
                    "status": "success"
                }
            })
            return
        # 查询指定码商的新手任务完成进度
        taskProgress = await self.getTaskProgress(self.current_user.id, prizeSetting.id)
        if not taskProgress:
            self.logger.info(f"current_user: {self.current_user}, taskProgress: {taskProgress}")
        for task in taskList:
            self.logger.info(f""" 任务: {task} """)
            # 匹配处理任务类型;1=register(注册),2=watch_tutorial_videos(观看引导视频),3=bind_upi(绑定UPI),4=order_success(成功代付订单)
            match task.type:
                case 1:
                    task.is_finished = False if taskProgress is None or taskProgress.time_set_trade_hash is None else True
                    task.time_finished = None if taskProgress is None or taskProgress.time_set_trade_hash is None else taskProgress.time_set_trade_hash
                case 2:
                    task.is_finished = False if taskProgress is None or taskProgress.time_watch_tutorial_videos is None else True
                    task.time_finished = None if taskProgress is None or taskProgress.time_watch_tutorial_videos is None else taskProgress.time_watch_tutorial_videos
                case 3:
                    task.is_finished = False if taskProgress is None or taskProgress.time_bind_upi is None else True
                    task.time_finished = None if taskProgress is None or taskProgress.time_bind_upi is None else taskProgress.time_bind_upi
                case 4:
                    task.is_finished = False if taskProgress is None or taskProgress.time_order_success is None else True
                    task.time_finished = None if taskProgress is None or taskProgress.time_order_success is None else taskProgress.time_order_success
                case 5:
                    task.is_finished = False
                    task.time_finished = None
                case 6:
                    task.is_finished = False
                    task.time_finished = None
                case _:
                    task.is_finished = False
                    task.time_finished = None
        # self.write(taskList)
        prizeSettingPartnerBeginnerTutorialTaskSchema = PrizeSettingPartnerBeginnerTutorialTaskSchema(many=True)
        taskSchemaList = prizeSettingPartnerBeginnerTutorialTaskSchema.dump(taskList)
        result = {
            "data": {
                "message": f"ok",
                "status": "success",
                "isFinished": 0 if taskProgress is None or taskProgress.is_finished is None else taskProgress.is_finished,
                "isAwarded": 0 if taskProgress is None or taskProgress.is_awarded is None else taskProgress.is_awarded,
                "prizeAmount": 0 if taskProgress is None or taskProgress.prize_amount is None else float(taskProgress.prize_amount),
                "taskProgressList": taskSchemaList
            }
        }
        self.write(result)
"""
观看新手引导视频
1、查询进行中的新手活动
2、查询活动的所有任务
3、检查不同任务完成情况并记录
"""
class watchTutorialVideos(BeginnerTaskProgressHandler):

    @handle_errors
    async def post(self):
        await self.authenticate_current_user()
        self.logger.info("Request [POST] (/partner/watch_tutorial_videos), current_user: %s", self.current_user)
        # 查询一个进行中的新手任务活动
        prizeSetting = await self.get_activity()
        # 没有活动时，直接返回
        if not prizeSetting:
            self.write({
                "data": {
                    "message": f"ok",
                    "status": "success"
                }
            })
        current_time = datetime.now()
        self.logger.info(f"current_time: {current_time}, prizeSetting: {prizeSetting}")
        taskList = await self.queryTaskList(prizeSettingId = prizeSetting.id, taskStatusEnable = None)
        if not taskList:
            self.write({
                "data": {
                    "message": f"ok",
                    "status": "success"
                }
            })
        # 查询指定码商的新手任务完成进度
        taskProgress = await self.getTaskProgress(self.current_user.id, prizeSetting.id)
        if not taskProgress:
            self.write({
                "data": {
                    "message": f"ok",
                    "status": "success"
                }
            })
        for task in taskList:
            self.logger.info(f"""
                任务ID: {task.id}
                任务名称: {task.name}
                任务类型: {task.type}
                任务说明: {task.description}
                是否启用: {task.status_enable}
            """)

