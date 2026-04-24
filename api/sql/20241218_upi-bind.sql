CREATE TABLE `payment_upi_history` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `payment_id` int NOT NULL COMMENT 'payment.id',
  `partner_id` int NOT NULL COMMENT 'partner.id',
  `bank_id` int NOT NULL COMMENT 'bank_type.id',
  `upi` varchar(500) NOT NULL COMMENT 'upi',
  `time_create` datetime NOT NULL COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_payment_id_upi` (`payment_id`,`upi`) USING BTREE
) ENGINE=InnoDB COMMENT='payment UPI 变更历史';