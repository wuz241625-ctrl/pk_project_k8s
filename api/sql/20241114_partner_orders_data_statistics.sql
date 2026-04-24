-- ----------------------------
-- Table structure for statistics_daily_partner_orders_df
-- ----------------------------
DROP TABLE IF EXISTS `statistics_daily_partner_orders_df`;
CREATE TABLE `statistics_daily_partner_orders_df` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '自增ID',
  `partner_id` int NOT NULL COMMENT '码商ID',
  `stats_date` date NOT NULL COMMENT '统计日期',
  `order_total` int NOT NULL DEFAULT '0' COMMENT '订单总数',
  `order_success` int NOT NULL DEFAULT '0' COMMENT '成功订单数',
  `order_fail` int NOT NULL DEFAULT '0' COMMENT '失败订单数',
  `order_amount` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '订单总金额',
  `order_amount_success` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '成功金额',
  `order_amount_fail` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '失败金额',
  `order_poundage` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '手续费',
  `rate` decimal(12,2) DEFAULT NULL COMMENT '成功率',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uk_stats_date` (`partner_id`,`stats_date`) USING BTREE COMMENT '统计日期唯一索引'
) COMMENT='代付订单每日统计表';

-- ----------------------------
-- Table structure for statistics_daily_partner_orders_ds
-- ----------------------------
DROP TABLE IF EXISTS `statistics_daily_partner_orders_ds`;
CREATE TABLE `statistics_daily_partner_orders_ds` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '自增ID',
  `partner_id` int NOT NULL COMMENT '码商ID',
  `stats_date` date NOT NULL COMMENT '统计日期',
  `order_total` int NOT NULL DEFAULT '0' COMMENT '订单总数',
  `order_success` int NOT NULL DEFAULT '0' COMMENT '成功订单数',
  `order_fail` int NOT NULL DEFAULT '0' COMMENT '失败订单数',
  `order_amount` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '订单总金额',
  `order_amount_success` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '成功金额',
  `order_amount_fail` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '失败金额',
  `order_poundage` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '手续费',
  `rate` decimal(12,2) DEFAULT NULL COMMENT '成功率',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uk_stats_date` (`partner_id`,`stats_date`) USING BTREE COMMENT '统计日期唯一索引'
) COMMENT='代收订单每日统计表';