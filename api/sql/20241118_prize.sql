-- ----------------------------
-- Table structure for prize_earn_log
-- ----------------------------
DROP TABLE IF EXISTS `prize_earn_log`;
CREATE TABLE `prize_earn_log`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'id',
  `user_id` int NOT NULL COMMENT '用户id',
  `user_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '用户名',
  `prize_id` int NOT NULL COMMENT '活动id',
  `prize_detail_id` int NOT NULL COMMENT '活动详情id',
  `prize_title` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '活动标题',
  `money` decimal(10, 2) NOT NULL COMMENT '奖励金额',
  `created_at` datetime NOT NULL COMMENT '创建日期',
  PRIMARY KEY (`id`) USING BTREE
) COMMENT = '活动日志表';

-- ----------------------------
-- Table structure for prize_setting
-- ----------------------------
DROP TABLE IF EXISTS `prize_setting`;
CREATE TABLE `prize_setting`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '活动ID, 主键',
  `title` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '标题',
  `content` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL COMMENT '内容',
  `type` tinyint(1) NULL DEFAULT NULL COMMENT '活动类型，0 抽奖，1 金额满赠 ，2 单数满赠',
  `participant` varchar(4096) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '参与人员id；-1全部人员，指定人员：id使用逗号隔开',
  `pic` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '图片路径',
  `created_at` datetime NOT NULL COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `status` tinyint(1) NOT NULL DEFAULT 1 COMMENT '0:禁用, 1:启用',
  `begin_at` datetime NOT NULL COMMENT '起始时间',
  `end_at` datetime NOT NULL COMMENT '结束时间',
  PRIMARY KEY (`id`) USING BTREE
) COMMENT = '活动设置表' ;

-- ----------------------------
-- Table structure for prize_setting_detail
-- ----------------------------
DROP TABLE IF EXISTS `prize_setting_detail`;
CREATE TABLE `prize_setting_detail`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '奖励ID, 主键',
  `prize_id` int NOT NULL COMMENT '活动ID, 外键',
  `prize_title` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '活动标题',
  `title` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '奖励标题',
  `prize_limit_min` int NULL DEFAULT NULL COMMENT '活动触发下限',
  `prize_limit_max` int NULL DEFAULT NULL COMMENT '活动触发上限',
  `money` decimal(10, 2) NOT NULL DEFAULT 0.00 COMMENT '奖励金额',
  `ratio` float NOT NULL DEFAULT 0 COMMENT '奖励概率',
  `created_at` datetime NOT NULL COMMENT '创建时间',
  `updated_at` datetime NOT NULL COMMENT '更新时间',
  `status` tinyint(1) NOT NULL DEFAULT 1 COMMENT '0:禁用, 1:启用',
  PRIMARY KEY (`id`) USING BTREE
) COMMENT = '活动设置明细表';