ALTER TABLE `partner`
MODIFY COLUMN `hash_trade` varchar(128) NULL COMMENT '交易' AFTER `hash_login`;

ALTER TABLE `prize_setting`
MODIFY COLUMN `type` tinyint(1) NULL DEFAULT NULL COMMENT '活动类型，0 抽奖，1 金额满赠，2 单数满赠，3 新手活动' AFTER `content`;

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
  `create_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uk_prize_id_partner_id` (`prize_id`,`partner_id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COMMENT='活动-码商-参加新手活动结果记录';

CREATE TABLE `prize_setting_partner_beginner_tutorial_task` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '任务ID',
  `prize_id` int NOT NULL COMMENT '活动设置ID，即prize_setting.id',
  `name` varchar(255) DEFAULT NULL COMMENT '任务名称',
  `type` tinyint DEFAULT NULL COMMENT '任务类型;1=set_trade_hash(设定支付安全码),2=watch_tutorial_videos(观看引导视频),3=bind_upi(绑定UPI),4=order_success(成功代付订单)',
  `status_enable` tinyint DEFAULT '0' COMMENT '是否启用;0=是,1=否',
  `description` longtext COMMENT '任务说明',
  `json_parameters` varchar(5000) DEFAULT NULL COMMENT '自定义参数',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime DEFAULT NULL COMMENT '修改时间',
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_prize_id` (`prize_id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 ROW_FORMAT=DYNAMIC COMMENT='活动设置表-新手引导任务';