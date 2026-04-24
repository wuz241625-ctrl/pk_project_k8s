from sqlalchemy import Column, DateTime, Integer, text
from sqlalchemy.dialects.mysql import LONGTEXT, TINYINT, VARCHAR
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, relationship

from application.lakshmi_api.models.prize_setting import PrizeSetting

Base = declarative_base()
metadata = Base.metadata

class PrizeSettingPartnerBeginnerTutorialTask(Base):
    __tablename__ = 'prize_setting_partner_beginner_tutorial_task'
    __table_args__ = {'comment': '活动设置表-新手引导任务'}

    id = Column(Integer, primary_key=True, comment='任务ID')
    prize_id = Column(Integer, nullable=False, comment='活动设置ID，即prize_setting.id')
    name = Column(VARCHAR(255), comment='任务名称')
    type = Column(TINYINT,
                  comment='任务类型;1=register(注册),2=watch_tutorial_videos(观看引导视频),3=bind_upi(绑定UPI),4=order_success(成功代付订单)')
    status_enable = Column(TINYINT, server_default=text("'0'"), comment='是否启用;0=是,1=否')
    description = Column(LONGTEXT, comment='任务说明')
    json_parameters = Column(VARCHAR(5000), comment='自定义参数')
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), comment='创建时间')
    updated_at = Column(DateTime, comment='修改时间')

    # 码商是否已完成此步任务
    _is_finished = False
    # 码商完成此步任务的时间
    _time_finished = None


    @hybrid_property
    def is_finished(self):
        return self._is_finished

    @is_finished.setter
    def is_finished(self, value):
        self._is_finished = value


    @hybrid_property
    def time_finished(self):
        return self._time_finished

    @time_finished.setter
    def time_finished(self, value):
        self._time_finished = value
    # prizeSetting: Mapped[PrizeSetting] = relationship("PrizeSetting",
    #                                                     back_populates="prizeSettingPartnerBeginnerTutorialTaskList")


""" sql
# 对应表结构
CREATE TABLE `prize_setting_partner_beginner_tutorial_task` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '任务ID',
  `prize_id` int NOT NULL COMMENT '活动设置ID，即prize_setting.id',
  `name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL COMMENT '任务名称',
  `type` tinyint DEFAULT NULL COMMENT '任务类型;1=register(注册),2=watch_tutorial_videos(观看引导视频),3=bind_upi(绑定UPI),4=order_success(成功代付订单)',
  `status_enable` tinyint DEFAULT '0' COMMENT '是否启用;0=是,1=否',
  `description` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci COMMENT '任务说明',
  `json_parameters` varchar(5000) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL COMMENT '自定义参数',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime DEFAULT NULL COMMENT '修改时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='活动设置表-新手引导任务';
"""
