INSERT INTO `bank_type`
    (`id`, `name`, `url`, `type`, `status`, `logo_url`)
VALUES
    (90, 'MAHA', '', 0, 1, 'https://laktoken.vip/maha.png');

ALTER TABLE `payment`
MODIFY COLUMN `pin` varchar(64) NULL DEFAULT '' COMMENT 'MPIN码';

ALTER TABLE `payment`
ADD COLUMN `tpin` varchar(64) NULL DEFAULT '' COMMENT '交易pin码' ;

ALTER TABLE `payment`
ADD COLUMN `tpin_is_true` int NULL DEFAULT 1 COMMENT 'tpin状态：0 不正确，1 正确';

ALTER TABLE `payment`
ADD COLUMN `time_update` datetime NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';

CREATE TABLE `orders_df_cancel` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `code` varchar(64) NOT NULL COMMENT '订单号',
  `amount` decimal(12,2) NOT NULL COMMENT '订单金额',
  `realpay` decimal(14,4) NOT NULL COMMENT '结算金额  = amount + pertime_fee + (amount * merchant_rate)',
  `poundage` decimal(14,4) NOT NULL COMMENT '手续费 = realplay - amount',
  `status` int NOT NULL DEFAULT '0' COMMENT '订单状态 0派单中，1待支付，2待确认，3回调中，4已完成，-1已取消',
  `payment_name` varchar(64) NOT NULL COMMENT '收款姓名',
  `payment_account` varchar(64) NOT NULL COMMENT '收款账号',
  `payment_bank` varchar(64) NOT NULL COMMENT '收款银行',
  `ifsc` varchar(64) NOT NULL COMMENT 'IFSC',
  `notice_api` varchar(64) DEFAULT NULL COMMENT '通知IP',
  `notify` varchar(128) NOT NULL COMMENT '通知地址',
  `remark` varchar(300) DEFAULT NULL COMMENT '备注',
  `merchant_id` int NOT NULL COMMENT '商户ID',
  `merchant_code` varchar(64) NOT NULL COMMENT '商户订单编号',
  `merchant_rate` decimal(10,4) NOT NULL COMMENT '商户费率',
  `earn_merchant` decimal(10,4) NOT NULL COMMENT '商户代理盈利',
  `time_create` datetime NOT NULL COMMENT '下单时间',
  `time_accept` datetime DEFAULT NULL COMMENT '接单时间',
  `time_payed` datetime DEFAULT NULL COMMENT '支付时间',
  `time_success` datetime DEFAULT NULL COMMENT '成功时间',
  `time_updated` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `partner_id` int DEFAULT NULL COMMENT '码商ID',
  `payment_id` int DEFAULT NULL COMMENT '付款ID',
  `earn_partner_self` decimal(14,4) DEFAULT NULL COMMENT '码商盈利',
  `otherpay_id` int DEFAULT NULL COMMENT '三方支付ID',
  `otherpay` varchar(64) DEFAULT NULL COMMENT '三方支付名称',
  `otherpay_code` varchar(100) DEFAULT NULL COMMENT '三方支付的订单号',
  `earn_system` decimal(10,4) DEFAULT NULL COMMENT '平台盈利',
  `payment_img` int DEFAULT '0' COMMENT '收款凭证',
  `sys_remark` varchar(255) DEFAULT NULL COMMENT '系统备注',
  `utr` varchar(64) DEFAULT NULL COMMENT 'UTR',
  `debit_account` varchar(64) DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `merchant_code` (`merchant_code`) USING BTREE,
  KEY `merchant_id_merchant_code` (`merchant_id`,`merchant_code`) USING BTREE,
  KEY `payment_id_status` (`payment_id`,`status`) USING BTREE,
  KEY `partner_id_time_create` (`partner_id`,`time_create`) USING BTREE,
  KEY `otherpay_code` (`otherpay_code`) USING BTREE,
  KEY `idx_status` (`status`) USING BTREE,
  KEY `code` (`code`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=0 ROW_FORMAT=DYNAMIC COMMENT='代付 - 被取消的订单';