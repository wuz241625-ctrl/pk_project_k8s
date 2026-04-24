from sqlalchemy import Column, DECIMAL, DateTime, Integer, text
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()
metadata = Base.metadata


class PrizePartnerBeginnerTutorialTaskProgress(Base):
    __tablename__ = 'prize_partner_beginner_tutorial_task_progress'
    __table_args__ = {'comment': '活动-码商-参加新手活动结果记录'}

    id = Column(Integer, primary_key=True, comment='主键ID')
    prize_id = Column(Integer, nullable=False, comment='活动设置ID，即prize_setting.id')
    partner_id = Column(Integer, nullable=False, comment='码商ID')
    is_finished = Column(TINYINT(1), nullable=False, server_default=text("'0'"), comment='任务是否完成;0=否,1=是')
    is_awarded = Column(TINYINT(1), nullable=False, server_default=text("'0'"), comment='是否已经发放奖励;0=否,1=是')
    prize_amount = Column(DECIMAL(10, 2), comment='实际奖励额度')
    time_awarded = Column(DateTime, comment='奖励发放时间')
    time_register = Column(DateTime, comment='码商的注册时间')
    time_set_trade_hash = Column(DateTime, comment='设定支付安全码的时间')
    time_watch_tutorial_videos = Column(DateTime, comment='码商观看新手教程视频的时间')
    time_bind_upi = Column(DateTime, comment='关联upi的时间')
    time_order_success = Column(DateTime, comment='完成一笔订单购买的时间')
    create_at = Column(DateTime, nullable=False, comment='创建时间')


""" sql
# 对应表结构
CREATE TABLE `prize_partner_beginner_tutorial_task_progress` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `prize_id` int NOT NULL COMMENT '活动设置ID，即prize_setting.id',
  `partner_id` int NOT NULL COMMENT '码商ID',
  `is_finished` tinyint(1) NOT NULL DEFAULT '0' COMMENT '任务是否完成;0=否,1=是',
  `is_awarded` tinyint(1) NOT NULL DEFAULT '0' COMMENT '是否已经发放奖励;0=否,1=是',
  `prize_amount` decimal(10,2) DEFAULT NULL COMMENT '实际奖励额度',
  `time_awarded` datetime DEFAULT NULL COMMENT '奖励发放时间',
  `time_register` datetime DEFAULT NULL COMMENT '码商的注册时间',
  `time_set_trade_hash` datetime DEFAULT NULL COMMENT '设定支付安全码的时间',
  `time_watch_tutorial_videos` datetime DEFAULT NULL COMMENT '码商观看新手教程视频的时间',
  `time_bind_upi` datetime DEFAULT NULL COMMENT '关联upi的时间',
  `time_order_success` datetime DEFAULT NULL COMMENT '完成一笔订单购买的时间',
  `create_at` datetime NOT NULL COMMENT '创建时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='活动-码商-参加新手活动结果记录';
"""
