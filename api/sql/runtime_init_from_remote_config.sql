-- 由 scripts/dump_remote_init_sql_from_config.sh 自动生成
-- 来源: root@34.96.148.205:/www/python/api/config.py
-- RUN_ENV: PRODUTION
-- 说明: schema-only init sql, 不包含线上业务数据


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

CREATE DATABASE /*!32312 IF NOT EXISTS*/ `pakistan` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci */ /*!80016 DEFAULT ENCRYPTION='N' */;

USE `pakistan`;
DROP TABLE IF EXISTS `_prisma_migrations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `_prisma_migrations` (
  `id` varchar(36) NOT NULL,
  `checksum` varchar(64) NOT NULL,
  `finished_at` datetime(3) DEFAULT NULL,
  `migration_name` varchar(255) NOT NULL,
  `logs` text,
  `rolled_back_at` datetime(3) DEFAULT NULL,
  `started_at` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `applied_steps_count` int unsigned NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `admin`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `admin` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `account` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '账户',
  `hash_login` varchar(128) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '密码hash',
  `name` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '名称',
  `role` int NOT NULL COMMENT '角色',
  `ggkey` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '谷歌密钥',
  `status` int NOT NULL DEFAULT '1' COMMENT '0禁用 1正常',
  `time_update` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间 ',
  `time_create` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `parent_id` int DEFAULT NULL COMMENT '推广人员关联商户的ID',
  `admin_id` int DEFAULT '1' COMMENT '添加的管理员编号',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `account` (`account`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=348 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci COMMENT='管理员';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `auto_payout_risk_config`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `auto_payout_risk_config` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '配置ID',
  `max_single_amount` decimal(10,2) DEFAULT '10000.00' COMMENT '最大单笔金额（实时控制）',
  `daily_order_count` int DEFAULT '100' COMMENT '单日笔数限制（实时控制）',
  `daily_total_amount` decimal(15,2) DEFAULT '200000.00' COMMENT '单日总金额限制（实时控制）',
  `min_amount` decimal(10,2) DEFAULT '100.00' COMMENT '收款最低金额',
  `max_amount` decimal(10,2) DEFAULT '50000.00' COMMENT '收款最高金额',
  `balance_limit` decimal(15,2) DEFAULT '300000.00' COMMENT '余额上限（5分钟延迟）',
  `enable_risk_control` tinyint(1) DEFAULT '1' COMMENT '是否启用风控检查',
  `enable_detailed_logs` tinyint(1) DEFAULT '1' COMMENT '是否启用详细日志',
  `enable_balance_warning` tinyint(1) DEFAULT '1' COMMENT '余额超限是否发送警告',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `updated_by` varchar(100) DEFAULT NULL COMMENT '更新人',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='自动代付风控参数配置表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `auto_payout_system_status`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `auto_payout_system_status` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '状态ID',
  `system_status` enum('running','stopped','maintenance') DEFAULT 'stopped' COMMENT '系统状态：运行中、已停止、维护中',
  `online_accounts` int DEFAULT '0' COMMENT '在线账号数量',
  `pending_orders` int DEFAULT '0' COMMENT '待处理订单数量',
  `today_success_orders` int DEFAULT '0' COMMENT '今日成功订单数',
  `today_total_amount` decimal(15,2) DEFAULT '0.00' COMMENT '今日成功总金额',
  `today_processed_orders` int DEFAULT '0' COMMENT '今日处理总订单数',
  `success_rate` decimal(5,2) DEFAULT '0.00' COMMENT '成功率（百分比）',
  `last_update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='自动代付系统状态表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `balance_count_record`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `balance_count_record` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `balance_p` decimal(14,4) NOT NULL COMMENT '码商余额',
  `balance_p_frozen` decimal(14,4) NOT NULL COMMENT '码商冻结余额',
  `balance_p_deposit` decimal(14,4) NOT NULL COMMENT '码商押金',
  `balance_m` decimal(14,4) NOT NULL COMMENT '商户余额',
  `balance_m_frozen` decimal(14,4) NOT NULL COMMENT '商户冻结余额',
  `created` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `balance_p_frozen_outside` decimal(14,4) NOT NULL COMMENT '外部码商冻结余额',
  `balance_p_outside` decimal(14,4) NOT NULL COMMENT '外部码商余额',
  `balance_p_inside` decimal(14,4) NOT NULL COMMENT '内部码商余额',
  `balance_p_frozen_inside` decimal(14,4) NOT NULL COMMENT '内部码商冻结余额',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=657 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci COMMENT='余额统计';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `balance_discrepancy_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `balance_discrepancy_log` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `user_id` int NOT NULL COMMENT '用户ID',
  `user_type` int NOT NULL COMMENT '用户类型 0码商 1商户',
  `recorded_balance` decimal(14,4) NOT NULL COMMENT '流水记录的余额',
  `actual_balance` decimal(14,4) NOT NULL COMMENT '数据库中的真实余额',
  `difference` decimal(14,4) NOT NULL COMMENT '差异',
  `time_checked` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '检查时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='余额不匹配日志表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `balance_record`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `balance_record` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `code` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '流水号',
  `change_before` decimal(14,4) NOT NULL COMMENT '帐变前',
  `amount` decimal(14,4) NOT NULL COMMENT '帐变金额',
  `change_after` decimal(14,4) NOT NULL COMMENT '帐变后',
  `record_type` int NOT NULL DEFAULT '0' COMMENT '流水类型 0代收 1代付 2提现 3佣金 4冻结 5押金 6人工 7充值 8转账',
  `admin_id` int DEFAULT NULL COMMENT '操作员ID',
  `user_type` int DEFAULT NULL COMMENT '用户类型  0码商 1商户',
  `user_id` int DEFAULT NULL COMMENT '用户ID',
  `remark` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '备注',
  `time_create` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `merchant_code` varchar(100) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '商户的订单号',
  PRIMARY KEY (`id`) USING BTREE,
  KEY `time_create` (`time_create`) USING BTREE,
  KEY `code` (`code`) USING BTREE,
  KEY `balance_record_user_id_index` (`user_id`)
) ENGINE=InnoDB AUTO_INCREMENT=9354220 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci COMMENT='余额流水';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `bank_ifsc`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `bank_ifsc` (
  `BANK` varchar(255) DEFAULT NULL,
  `IFSC` varchar(50) DEFAULT NULL,
  `BRANCH` varchar(255) DEFAULT NULL,
  `CENTRE` varchar(255) DEFAULT NULL,
  `DISTRICT` varchar(255) DEFAULT NULL,
  `STATE` varchar(255) DEFAULT NULL,
  `ADDRESS` varchar(255) DEFAULT NULL,
  `CONTACT` varchar(255) DEFAULT NULL,
  `IMPS` varchar(255) DEFAULT NULL,
  `RTGS` varchar(255) DEFAULT NULL,
  `CITY` varchar(255) DEFAULT NULL,
  `ISO3166` varchar(255) DEFAULT NULL,
  `NEFT` varchar(255) DEFAULT NULL,
  `MICR` int DEFAULT NULL,
  `UPI` varchar(255) DEFAULT NULL,
  `SWIFT` varchar(255) DEFAULT NULL,
  UNIQUE KEY `ifsc` (`IFSC`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `bank_record`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `bank_record` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `admin_id` int DEFAULT NULL COMMENT '管理员ID',
  `payment_id` int NOT NULL COMMENT '银行卡ID',
  `amount` decimal(12,2) NOT NULL COMMENT '交易金额',
  `content` varchar(1280) DEFAULT NULL COMMENT '采集内容',
  `trade_type` int NOT NULL DEFAULT '0' COMMENT '交易类型 0解析失败 1收 2付 3付退 4付相关 ',
  `utr` varchar(32) DEFAULT NULL COMMENT 'UTR',
  `code` varchar(100) DEFAULT NULL COMMENT '确认码/卡后4位',
  `ifsc` varchar(32) DEFAULT NULL COMMENT 'IFSC',
  `order_code` varchar(64) DEFAULT NULL COMMENT '订单号',
  `callback` int NOT NULL DEFAULT '0' COMMENT '回调结果',
  `invalid` int DEFAULT '0' COMMENT '失效',
  `time_create` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `ew_code` varchar(64) DEFAULT NULL COMMENT '额外流水号',
  `partner_id` int NOT NULL COMMENT '码商id',
  `if_ew` tinyint DEFAULT '0' COMMENT 'ew_code为空则为0，不为空则为1',
  `memo` varchar(255) DEFAULT NULL COMMENT '备注',
  `trans_id` varchar(128) DEFAULT NULL COMMENT '交易ID',
  PRIMARY KEY (`id`) USING BTREE,
  KEY `utr` (`utr`) USING BTREE,
  KEY `ind_partner_id_time_create` (`partner_id`,`time_create`) USING BTREE,
  KEY `payment_id_trade_type_if_ew_invalid_callback` (`payment_id`,`trade_type`,`if_ew`,`invalid`,`callback`) USING BTREE,
  KEY `trans_id` (`trans_id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=1130347 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `bank_type`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `bank_type` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `name` varchar(32) DEFAULT NULL COMMENT '银行名称',
  `url` varchar(255) DEFAULT NULL COMMENT '网银登录地址',
  `type` int DEFAULT '0' COMMENT '显示类型 0内部码商显示 1外部显示',
  `status` tinyint(1) DEFAULT '1' COMMENT '0禁用1启用',
  `logo_url` varchar(191) DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=99 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='银行卡类型表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `bank_type_copy1`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `bank_type_copy1` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `name` varchar(32) DEFAULT NULL COMMENT '银行名称',
  `url` varchar(255) DEFAULT NULL COMMENT '网银登录地址',
  `type` int DEFAULT '0' COMMENT '显示类型 0内部码商显示 1外部显示',
  `status` tinyint(1) DEFAULT '1' COMMENT '0禁用1启用',
  `logo_url` varchar(191) DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=100 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='银行卡类型表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `bank_type_setting`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `bank_type_setting` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `name` varchar(32) DEFAULT NULL COMMENT '银行名称',
  `type` int DEFAULT '0' COMMENT '显示类型 0内部码商显示 1外部显示',
  `max_sec` int DEFAULT '0' COMMENT '多长时间接单',
  `max_count` int DEFAULT '0' COMMENT '最大接单次数',
  `status` tinyint(1) DEFAULT '1' COMMENT '0禁用1启用',
  `bank_id` int DEFAULT '0' COMMENT '银行编号',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=25 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='银行卡系统设置表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `bank_type_setting_copy1`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `bank_type_setting_copy1` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `name` varchar(32) DEFAULT NULL COMMENT '银行名称',
  `type` int DEFAULT '0' COMMENT '显示类型 0内部码商显示 1外部显示',
  `max_sec` int DEFAULT '0' COMMENT '多长时间接单',
  `max_count` int DEFAULT '0' COMMENT '最大接单次数',
  `status` tinyint(1) DEFAULT '1' COMMENT '0禁用1启用',
  `bank_id` int DEFAULT '0' COMMENT '银行编号',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=25 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='银行卡系统设置表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `bank_withdrawal`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `bank_withdrawal` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `admin_id` int DEFAULT NULL COMMENT '管理员ID',
  `payment_id` int NOT NULL COMMENT '银行卡ID',
  `s_payment_id` int DEFAULT NULL COMMENT '收款银行卡ID',
  `amount` decimal(12,2) NOT NULL COMMENT '交易金额',
  `utr` varchar(32) DEFAULT NULL COMMENT 'UTR',
  `time_create` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `partner_id` int NOT NULL COMMENT '码商id',
  `tran_date` varchar(20) DEFAULT NULL COMMENT '转账日期',
  `memo` varchar(255) DEFAULT NULL COMMENT '备注',
  PRIMARY KEY (`id`) USING BTREE,
  KEY `utr` (`utr`) USING BTREE,
  KEY `ind_partner_id_time_create` (`partner_id`,`time_create`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=235 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='银行出款采集';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `cd_types`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `cd_types` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(64) NOT NULL,
  `description` varchar(2000) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=12 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='查单设置表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `channel`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `channel` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `code` int NOT NULL COMMENT '网关号',
  `name` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '通道名称',
  `type` int NOT NULL COMMENT '0二维码 1银行卡',
  `url` varchar(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '图标路径',
  `rate` decimal(14,4) NOT NULL COMMENT '码商费率',
  `rates` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '码商代理层级费率',
  `amount_min` decimal(12,2) DEFAULT NULL COMMENT '最小金额',
  `amount_max` decimal(12,2) DEFAULT NULL COMMENT '最大金额',
  `amount_fixed` varchar(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '固定金额',
  `fixed` int NOT NULL COMMENT '是否固额',
  `status` int NOT NULL DEFAULT '1' COMMENT '0禁用 1正常',
  `decimal_callback_enabled` tinyint(1) DEFAULT '0' COMMENT '是否为小数点回调通道 0-否 1-是',
  `time_update` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间 ',
  `time_create` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `decimal_min` decimal(3,2) DEFAULT '0.01' COMMENT '小数点范围最小值',
  `decimal_max` decimal(3,2) DEFAULT '0.99' COMMENT '小数点范围最大值',
  `is_show_qr` tinyint(1) DEFAULT '0' COMMENT '0/1 是否显示二维码   不显示/显示',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `code` (`code`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci COMMENT='通道';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `daily`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `daily` (
  `id` int NOT NULL AUTO_INCREMENT,
  `date` date NOT NULL COMMENT '日期',
  `balance_type` int NOT NULL COMMENT '余额类型 0码商余额 1商户余额',
  `record_type` int NOT NULL COMMENT '流水类型 0代收 1代付 2提现 3佣金 4冻结 5押金 6人工',
  `amount` decimal(14,4) NOT NULL COMMENT '总金额',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=6701 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci COMMENT='财务报表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `easypaisa_operation_logs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `easypaisa_operation_logs` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '日志ID',
  `from_payment_id` varchar(50) DEFAULT NULL COMMENT '转出方payment_id',
  `from_account_number` varchar(50) DEFAULT NULL COMMENT '转出方EasyPaisa手机号',
  `to_account_number` varchar(100) DEFAULT NULL COMMENT '转入账号(手机号或银行卡号)',
  `to_account_name` varchar(100) DEFAULT NULL COMMENT '收款人姓名',
  `to_bank_code` varchar(50) DEFAULT NULL COMMENT '银行代码(IFSC等)',
  `to_bank_name` varchar(100) DEFAULT NULL COMMENT '银行名称',
  `order_code` varchar(100) DEFAULT NULL COMMENT '关联订单号',
  `operation_type` varchar(50) NOT NULL COMMENT '操作类型：login,logout,transfer_same_bank,transfer_cross_bank,balance_check等',
  `transfer_type` varchar(50) DEFAULT NULL COMMENT '转账类型：EasyPaisa同行转账,跨行转账到银行卡',
  `amount` decimal(12,2) DEFAULT NULL COMMENT '操作金额',
  `currency` varchar(10) DEFAULT 'PKR' COMMENT '货币类型',
  `transaction_id` varchar(100) DEFAULT NULL COMMENT 'EasyPaisa交易ID',
  `reference_number` varchar(100) DEFAULT NULL COMMENT '参考号',
  `status` varchar(20) NOT NULL COMMENT '操作状态：success,failed,pending',
  `before_balance` decimal(12,2) DEFAULT NULL COMMENT '操作前余额',
  `after_balance` decimal(12,2) DEFAULT NULL COMMENT '操作后余额',
  `api_request` text COMMENT 'API请求数据(JSON)',
  `api_response` text COMMENT 'API响应数据(JSON)',
  `api_endpoint` varchar(200) DEFAULT NULL COMMENT 'API端点路径',
  `request_uuid` varchar(50) DEFAULT NULL COMMENT '请求UUID',
  `error_code` varchar(20) DEFAULT NULL COMMENT '错误代码',
  `error_message` text COMMENT '错误信息',
  `process_time` int DEFAULT NULL COMMENT '处理耗时（毫秒）',
  `retry_count` int DEFAULT '0' COMMENT '重试次数',
  `ip_address` varchar(45) DEFAULT NULL COMMENT '服务器IP地址',
  `user_agent` varchar(500) DEFAULT NULL COMMENT '用户代理',
  `server_process_id` int DEFAULT NULL COMMENT '处理进程ID',
  `trace_id` varchar(50) DEFAULT NULL COMMENT '链路追踪ID',
  `process_log` text COMMENT '完整流程日志(JSON格式)',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_from_payment_id` (`from_payment_id`),
  KEY `idx_order_code` (`order_code`),
  KEY `idx_operation_type` (`operation_type`),
  KEY `idx_transaction_id` (`transaction_id`),
  KEY `idx_status` (`status`),
  KEY `idx_created_at` (`created_at`),
  KEY `idx_amount` (`amount`),
  KEY `idx_trace_id` (`trace_id`)
) ENGINE=InnoDB AUTO_INCREMENT=649144 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='EasyPaisa操作日志表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `error_messages`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `error_messages` (
  `error_code` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `module` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `severity` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `technical_message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `zh_title` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `zh_message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `zh_action` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `en_title` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `en_message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `en_action` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `hi_title` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `hi_message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `hi_action` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`error_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='错误信息表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `lakshmi_api_settings`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `lakshmi_api_settings` (
  `id` int NOT NULL AUTO_INCREMENT,
  `genre` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `value` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `merchant`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `merchant` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NOT NULL COMMENT '昵称',
  `cellphone` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NOT NULL COMMENT '手机号',
  `hash_login` varchar(128) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NOT NULL COMMENT '登录',
  `gg_key` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NOT NULL COMMENT 'google验证key',
  `balance` decimal(14,4) NOT NULL DEFAULT '0.0000' COMMENT '余额',
  `balance_frozen` decimal(14,4) NOT NULL DEFAULT '0.0000' COMMENT '余额冻结',
  `fee_df` decimal(14,4) NOT NULL DEFAULT '0.0000' COMMENT '代付单笔费用',
  `rate_df` decimal(14,4) NOT NULL DEFAULT '0.0000' COMMENT '代付费率',
  `mc_key` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NOT NULL COMMENT 'Order key',
  `return_url` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否返回链接',
  `status` int NOT NULL DEFAULT '1' COMMENT '0禁用(默认) 1启用',
  `status_df` int NOT NULL DEFAULT '0' COMMENT '代付状态',
  `decimal_amt_flag` tinyint(1) DEFAULT '0' COMMENT '商户小数点回调开关 0-关闭 1-开启',
  `notify_callback_type` tinyint(1) DEFAULT '0' COMMENT 'Notify回调类型 0-整数回调 1-小数点回调',
  `pid` int DEFAULT NULL COMMENT '上级ID',
  `target_payment` varchar(2000) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '专卡专户，对代收和代付同时生效',
  `ip` varchar(1000) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci DEFAULT NULL COMMENT 'IP白名单',
  `ip_df` varchar(1000) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '代付白名单',
  `time_update` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `time_create` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `amount_fixed` decimal(10,2) DEFAULT '0.00' COMMENT '代付固定金额',
  `ds_on` tinyint(1) DEFAULT '1' COMMENT '0/1 开启/关闭(代收黑名单)',
  `ds_black_ips` varchar(1000) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '代收黑名单',
  `ds_userid_on` tinyint(1) DEFAULT '1' COMMENT '0/1 开启/关闭(代收user_id黑名单)',
  `ds_black_userids` varchar(1000) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '代收user_id黑名单',
  `receive_point_amt_flag` tinyint(1) NOT NULL DEFAULT '0' COMMENT '0禁用1启用小数点回调',
  `amount_fixed_max` decimal(10,2) DEFAULT '0.00' COMMENT '代付单笔最大额度',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `name` (`name`) USING BTREE,
  UNIQUE KEY `cellphone` (`cellphone`) USING BTREE,
  UNIQUE KEY `time_create` (`time_create`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=311 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci COMMENT='商户';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `merchant_channel`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `merchant_channel` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `merchant_id` int NOT NULL COMMENT '商户ID',
  `code` int NOT NULL COMMENT '网关号',
  `rate` decimal(14,4) NOT NULL COMMENT '费率',
  `otherpay` int DEFAULT NULL COMMENT '三方支付',
  `is_force` int DEFAULT '0' COMMENT '是否强制三方',
  `target_channel` int DEFAULT NULL COMMENT '通道跳转',
  `status` int DEFAULT '1' COMMENT '状态',
  PRIMARY KEY (`id`) USING BTREE,
  KEY `merchant_id` (`merchant_id`) USING BTREE,
  KEY `merchant_id_code_status` (`merchant_id`,`code`,`status`) USING BTREE,
  KEY `code` (`code`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=389 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci COMMENT='商户通道';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `merchant_pay_links`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `merchant_pay_links` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `pay_name` varchar(50) NOT NULL,
  `pay_link` varchar(512) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='后台商户支付链接';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `merchant_tree`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `merchant_tree` (
  `parent` int NOT NULL,
  `child` int NOT NULL,
  `distance` int NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci COMMENT='商户结构';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `merchant_withdraw`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `merchant_withdraw` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `code` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '订单号',
  `merchant_id` int NOT NULL COMMENT '商户ID',
  `address` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '地址',
  `amount` decimal(12,2) NOT NULL COMMENT '订单金额',
  `status` int NOT NULL DEFAULT '0' COMMENT '状态 0下单 1处理 2完成 -1驳回',
  `time_success` datetime DEFAULT NULL COMMENT '成功时间',
  `time_updated` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `time_create` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '下单时间',
  `admin_id` int DEFAULT NULL COMMENT '管理员',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=112 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci COMMENT='商户提现';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `message`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `message` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `to_id` varchar(500) DEFAULT NULL COMMENT '接收用户ID,多个用逗号分隔,为空表示全员',
  `from_id` int NOT NULL COMMENT '发送人ID',
  `type` tinyint NOT NULL DEFAULT '1' COMMENT '消息类型:1系统通知 2业务消息',
  `subject` varchar(100) NOT NULL COMMENT '消息标题',
  `content` text NOT NULL COMMENT '消息内容',
  `send_time` datetime NOT NULL COMMENT '发送时间',
  `status` tinyint NOT NULL DEFAULT '1' COMMENT '状态:1待发送 2已发送',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=789 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='站内信消息主表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `operate`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `operate` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `type` int DEFAULT NULL COMMENT '操作类型 1登录 2修改权限 3修改通道 4修改商户 5修改码商 6代收补单 7代付补单 8处理充值 9处理提现 10处理转账 11补单 12代付',
  `admin_id` int NOT NULL COMMENT '操作员ID',
  `ip` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT 'IP地址',
  `time_create` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '操作时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=671309 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci COMMENT='操作日志';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `operation_logs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `operation_logs` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `operator` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '操作人',
  `ip_address` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT 'IP地址',
  `operation_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '操作时间',
  `operation_button` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '操作按钮',
  `menu` varchar(128) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '菜单',
  `operation_content` varchar(2000) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '操作内容',
  PRIMARY KEY (`id`) USING BTREE,
  KEY `operator` (`operator`) USING BTREE,
  KEY `operation_time` (`operation_time`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=179 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='操作日志';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `order_pub_acct_payment`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `order_pub_acct_payment` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `wallet_id` varchar(20) DEFAULT NULL COMMENT '银行ID',
  `amount` decimal(12,2) DEFAULT NULL COMMENT '金额',
  `utr` varchar(12) DEFAULT NULL COMMENT 'UTR',
  `remark` varchar(255) DEFAULT NULL COMMENT '备注',
  `date` varchar(20) DEFAULT NULL COMMENT '转账日期',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `creator` bigint DEFAULT NULL COMMENT '创建人',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='公户出款';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `orders_cd`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `orders_cd` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `code` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '订单号',
  `amount` decimal(14,2) NOT NULL COMMENT '订单金额',
  `realpay` decimal(14,4) NOT NULL COMMENT '结算金额 amount  x merchant_rate',
  `poundage` decimal(14,4) NOT NULL COMMENT '手续费 = amount - realplay',
  `channel_code` int NOT NULL COMMENT '网关号',
  `status` int NOT NULL DEFAULT '0' COMMENT '订单状态 0派单中，1待支付，2待确认，3回调中，4已完成，-1已取消',
  `callback` varchar(128) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NOT NULL COMMENT '回调地址',
  `notice_api` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci DEFAULT NULL COMMENT '通知IP',
  `notify` varchar(256) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NOT NULL COMMENT '通知地址',
  `player_ip` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci DEFAULT NULL COMMENT '客户IP地址',
  `remark` varchar(300) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci DEFAULT NULL COMMENT '备注',
  `pay_url` varchar(128) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci DEFAULT NULL COMMENT '支付地址',
  `time_create` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '下单时间',
  `time_accept` datetime DEFAULT NULL COMMENT '接单时间',
  `time_payed` datetime DEFAULT NULL COMMENT '支付时间',
  `time_success` datetime DEFAULT NULL COMMENT '成功时间',
  `merchant_id` int NOT NULL COMMENT '商户ID',
  `merchant_code` varchar(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL,
  `merchant_rate` decimal(10,4) DEFAULT '0.0000' COMMENT '商户费率',
  `earn_merchant` decimal(10,4) DEFAULT '0.0000' COMMENT '商户总盈利',
  `partner_id` int DEFAULT NULL COMMENT '码商ID',
  `earn_partner_self` decimal(14,4) DEFAULT '0.0000' COMMENT '码商盈利',
  `earn_partner` decimal(10,4) DEFAULT '0.0000' COMMENT '码商总盈利',
  `payment_id` int DEFAULT NULL COMMENT '收款ID',
  `upi` text CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci COMMENT 'UPI',
  `utr` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT 'UTR',
  `auth_code` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '确认码',
  `realname` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci DEFAULT NULL COMMENT '用户真实姓名',
  `player_provence` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci DEFAULT NULL COMMENT '根据IP获取的省份信息',
  `otherpay` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '三方支付名称',
  `earn_system` decimal(10,4) DEFAULT '0.0000' COMMENT '平台盈利',
  `time_updated` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `cd_memo` varchar(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '查单备注',
  `cd_status` tinyint(1) DEFAULT '0' COMMENT '出单状态 0/1/2   待审核(反审核)/审核/确定审核',
  `is_cd` tinyint(1) DEFAULT '0' COMMENT '是否查单0/1   不是/是',
  `admin_id` int DEFAULT NULL COMMENT '操作员ID',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
  `cd_admin_id` int DEFAULT NULL COMMENT '查单人ID',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `code` (`code`) USING BTREE,
  KEY `merchant_code` (`merchant_code`) USING BTREE,
  KEY `merchant_id_merchant_code` (`merchant_id`,`merchant_code`) USING BTREE,
  KEY `payment_id_status_time_create` (`payment_id`,`status`,`time_create`) USING BTREE,
  KEY `auth_code` (`auth_code`) USING BTREE,
  KEY `id_time_create` (`id`,`time_create`) USING BTREE,
  KEY `time_create` (`time_create`) USING BTREE,
  KEY `merchant_id_status_time_create` (`status`,`time_create`,`merchant_id`) USING BTREE,
  KEY `merchant_id_time_create` (`merchant_id`,`time_create`) USING BTREE,
  KEY `time_success` (`time_success`) USING BTREE,
  KEY `utr_time_create` (`utr`,`time_create`) USING BTREE,
  KEY `amount_auth_code_status_time_create` (`amount`,`status`,`time_create`,`auth_code`) USING BTREE,
  KEY `order_withdraw_partner_id` (`partner_id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=105 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='查单';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `orders_df`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `orders_df` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `code` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '订单号',
  `amount` decimal(12,2) NOT NULL COMMENT '订单金额',
  `realpay` decimal(14,4) NOT NULL COMMENT '结算金额  = amount + pertime_fee + (amount * merchant_rate)',
  `poundage` decimal(14,4) NOT NULL COMMENT '手续费 = realplay - amount',
  `status` int NOT NULL DEFAULT '0' COMMENT '订单状态 0派单中，1待支付，2待确认，3回调中，4已完成，-1已取消',
  `payment_name` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '收款姓名',
  `payment_account` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '收款账号',
  `payment_bank` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '收款银行',
  `ifsc` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT 'IFSC',
  `notice_api` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '通知IP',
  `notify` varchar(128) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '通知地址',
  `remark` varchar(300) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '备注',
  `merchant_id` int NOT NULL COMMENT '商户ID',
  `merchant_code` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '商户订单编号',
  `merchant_rate` decimal(10,4) NOT NULL COMMENT '商户费率',
  `earn_merchant` decimal(10,4) NOT NULL COMMENT '商户代理盈利',
  `time_create` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '下单时间',
  `time_accept` datetime DEFAULT NULL COMMENT '接单时间',
  `time_payed` datetime DEFAULT NULL COMMENT '支付时间',
  `time_success` datetime DEFAULT NULL COMMENT '成功时间',
  `time_updated` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `partner_id` int DEFAULT NULL COMMENT '码商ID',
  `payment_id` int DEFAULT NULL COMMENT '付款ID',
  `earn_partner_self` decimal(14,4) DEFAULT NULL COMMENT '码商盈利',
  `otherpay_id` int DEFAULT NULL COMMENT '三方支付ID',
  `otherpay` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '三方支付名称',
  `otherpay_code` varchar(100) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '三方支付的订单号',
  `earn_system` decimal(10,4) DEFAULT NULL COMMENT '平台盈利',
  `payment_img` int DEFAULT '0' COMMENT '收款凭证',
  `sys_remark` varchar(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '系统备注',
  `utr` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT 'UTR',
  `debit_account` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL,
  `parent_id` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT '' COMMENT '父订单ID（0表示是主订单）',
  `is_split` tinyint DEFAULT '0' COMMENT '是否拆单处理（1为拆单；0：未拆单）',
  `is_del` tinyint(1) DEFAULT '0' COMMENT '0/1 1：删除',
  `payout_type` tinyint(1) NOT NULL DEFAULT '0' COMMENT '代付类型: 0=手动代付, 1=自动代付',
  `target_payment` varchar(2000) COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '如果对商户设置专卡专户，这里对每一个订单记录一致信息',
  `retry_count` int NOT NULL DEFAULT '0' COMMENT '重试次数: 记录代付订单的重试次数',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `code` (`code`) USING BTREE,
  KEY `merchant_code` (`merchant_code`) USING BTREE,
  KEY `merchant_id_merchant_code` (`merchant_id`,`merchant_code`) USING BTREE,
  KEY `payment_id_status` (`payment_id`,`status`) USING BTREE,
  KEY `time_accept` (`time_accept`) USING BTREE,
  KEY `partner_id_time_create` (`partner_id`,`time_create`) USING BTREE,
  KEY `order_deposit_partner_id` (`partner_id`) USING BTREE,
  KEY `otherpay_code` (`otherpay_code`) USING BTREE,
  KEY `idx_time_success` (`time_success`),
  KEY `idx_merchant_id` (`merchant_id`),
  KEY `idx_status` (`status`)
) ENGINE=InnoDB AUTO_INCREMENT=995610 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci ROW_FORMAT=DYNAMIC COMMENT='代付';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `orders_df_cancel`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
) ENGINE=InnoDB AUTO_INCREMENT=34 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='代付 - 被取消的订单';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `orders_ds`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `orders_ds` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `code` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '???',
  `amount` decimal(14,2) NOT NULL COMMENT '????',
  `realpay` decimal(14,4) NOT NULL COMMENT '???? amount  x merchant_rate',
  `poundage` decimal(14,4) NOT NULL COMMENT '??? = amount - realplay',
  `channel_code` int NOT NULL COMMENT '???',
  `status` int NOT NULL DEFAULT '0' COMMENT '???? 0????1????2????3????4????-1???',
  `callback` varchar(128) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NOT NULL COMMENT '????',
  `notice_api` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci DEFAULT NULL COMMENT '??IP',
  `notify` varchar(256) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NOT NULL COMMENT '????',
  `player_ip` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci DEFAULT NULL COMMENT '??IP??',
  `remark` varchar(300) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci DEFAULT NULL COMMENT '??',
  `pay_url` varchar(128) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci DEFAULT NULL COMMENT '????',
  `time_create` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '????',
  `time_accept` datetime DEFAULT NULL COMMENT '????',
  `time_payed` datetime DEFAULT NULL COMMENT '????',
  `time_success` datetime DEFAULT NULL COMMENT '????',
  `merchant_id` int NOT NULL COMMENT '??ID',
  `merchant_code` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '??????',
  `merchant_rate` decimal(10,4) DEFAULT '0.0000' COMMENT '????',
  `earn_merchant` decimal(10,4) DEFAULT '0.0000' COMMENT '?????',
  `partner_id` int DEFAULT NULL COMMENT '??ID',
  `earn_partner_self` decimal(14,4) DEFAULT '0.0000' COMMENT '????',
  `earn_partner` decimal(10,4) DEFAULT '0.0000' COMMENT '?????',
  `payment_id` int DEFAULT NULL COMMENT '??ID',
  `upi` varchar(500) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT 'UPI',
  `utr` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT 'UTR',
  `auth_code` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '???',
  `realname` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci DEFAULT NULL COMMENT '??????',
  `player_provence` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci DEFAULT NULL COMMENT '??IP???????',
  `otherpay` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '??????',
  `earn_system` decimal(10,4) DEFAULT '0.0000' COMMENT '????',
  `time_updated` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '????',
  `third_party_id` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT '',
  `third_party_order_number` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT '',
  `third_party_name` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT '' COMMENT 'otherpay?name',
  `user_id` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT 'user_id',
  `original_amount` decimal(14,4) DEFAULT NULL COMMENT '小数点回调订单的原始金额',
  `tax` decimal(10,4) DEFAULT '0.0000' COMMENT '税费',
  `trans_id` varchar(128) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '交易ID',
  `count_statics` varchar(1024) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '统计次数json格式',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `code` (`code`) USING BTREE,
  KEY `merchant_code` (`merchant_code`) USING BTREE,
  KEY `merchant_id_merchant_code` (`merchant_id`,`merchant_code`) USING BTREE,
  KEY `payment_id_status_time_create` (`payment_id`,`status`,`time_create`) USING BTREE,
  KEY `auth_code` (`auth_code`) USING BTREE,
  KEY `id_time_create` (`id`,`time_create`) USING BTREE,
  KEY `time_create` (`time_create`) USING BTREE,
  KEY `merchant_id_status_time_create` (`status`,`time_create`,`merchant_id`) USING BTREE,
  KEY `merchant_id_time_create` (`merchant_id`,`time_create`) USING BTREE,
  KEY `time_success` (`time_success`) USING BTREE,
  KEY `utr_time_create` (`utr`,`time_create`) USING BTREE,
  KEY `amount_auth_code_status_time_create` (`amount`,`status`,`time_create`,`auth_code`) USING BTREE,
  KEY `order_withdraw_partner_id` (`partner_id`) USING BTREE,
  KEY `trans_id` (`trans_id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=3347839 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci ROW_FORMAT=DYNAMIC COMMENT='??';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `otherpay`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `otherpay` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `merchant_id` varchar(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '商户ID',
  `key` varchar(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '密钥',
  `key2` varchar(2000) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '可以放公钥',
  `key3` varchar(2000) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '可以放私钥',
  `name` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '支付名称',
  `pay_url` varchar(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '网关',
  `channel_code` int DEFAULT NULL COMMENT '网关号',
  `notify_ip` varchar(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '回调IP',
  `query_url` varchar(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '查询网关',
  `forcible` int NOT NULL DEFAULT '0' COMMENT '是否强转',
  `status` int NOT NULL DEFAULT '1' COMMENT '0禁用 1正常',
  `updated` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间 ',
  `created` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=26 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci COMMENT='三方支付';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `partner`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `partner` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT ' ',
  `name` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL,
  `cellphone` varchar(32) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NOT NULL COMMENT '手机',
  `hash_login` varchar(128) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci NOT NULL COMMENT '登录',
  `hash_trade` varchar(128) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '交易',
  `balance` decimal(14,4) NOT NULL DEFAULT '0.0000' COMMENT '余额',
  `balance_frozen` decimal(14,4) NOT NULL DEFAULT '0.0000' COMMENT '冻结',
  `balance_deposit` decimal(14,4) NOT NULL DEFAULT '0.0000' COMMENT '押金',
  `vip` int NOT NULL DEFAULT '1' COMMENT 'VIP等级',
  `pid` int DEFAULT NULL COMMENT '上级代理',
  `status` int NOT NULL DEFAULT '1' COMMENT '1正常 0封禁',
  `certified` int NOT NULL DEFAULT '0' COMMENT '认证',
  `ip` int DEFAULT '0' COMMENT '注册IP',
  `time_update` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `time_create` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `type` int DEFAULT '1' COMMENT '码商类型 0内部 1外部 2高风险码商',
  `invitation_code` varchar(8) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '邀请码',
  `authentication_token` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL,
  `email` varchar(50) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL,
  `ds_min` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '代收最小限额',
  `ds_max` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '代收最大限额',
  `insufficient_balance` decimal(14,4) DEFAULT '500.0000' COMMENT '余额不足短信提醒触发值',
  `rates` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '层级费率',
  `negative_limit` decimal(14,2) NOT NULL DEFAULT '0.00' COMMENT '码商欠额上限(负数)',
  `banned` tinyint(1) NOT NULL DEFAULT '0' COMMENT '是否封号',
  `failed_login_attempts` int NOT NULL DEFAULT '0' COMMENT '错误登陆次数',
  `last_failed_login` datetime DEFAULT NULL COMMENT '最后登陆错误时间戳',
  `is_danger` tinyint(1) NOT NULL DEFAULT '0' COMMENT '是否高危用户：0 否 1是',
  `rate` decimal(14,4) DEFAULT NULL COMMENT '层级费率',
  `invitation_code_rate_config` varchar(2000) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '[]',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `invitation_code` (`invitation_code`) USING BTREE,
  KEY `name` (`name`) USING BTREE,
  KEY `cellphone` (`cellphone`) USING BTREE,
  KEY `time_create` (`time_create`) USING BTREE,
  KEY `pid` (`pid`) USING BTREE,
  KEY `authentication_token` (`authentication_token`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=33056 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci COMMENT='码商';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `partner_invitation_code`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `partner_invitation_code` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT ' ',
  `partner_id` int NOT NULL COMMENT '码商id',
  `invitation_code` varchar(8) NOT NULL COMMENT '邀请码',
  `rate` decimal(14,4) NOT NULL DEFAULT '0.0000' COMMENT '邀请码费率',
  `time_update` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `time_create` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `invitation_code` (`invitation_code`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='码商邀请码和费率';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `partner_login_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `partner_login_log` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `partner_id` int NOT NULL COMMENT '码商ID',
  `ip` varchar(45) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '登录IP',
  `ref` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '访问站点',
  `loc` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'IP位置',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '登录时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=1484 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='码商登录历史记录';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `partner_recharge`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `partner_recharge` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `code` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '订单号',
  `partner_id` int NOT NULL COMMENT '码商ID',
  `amount` decimal(12,2) NOT NULL COMMENT '订单金额',
  `admin_id` int DEFAULT NULL COMMENT '管理员ID',
  `status` int NOT NULL DEFAULT '0' COMMENT '订单状态 0待处理 1处理中 2已完成 -1已取消',
  `time_success` datetime DEFAULT NULL COMMENT '成功时间',
  `time_updated` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `time_create` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '下单时间',
  `sys_payment_id` int DEFAULT NULL COMMENT '系统卡ID',
  `ifsc` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT 'ifsc',
  `account` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT 'account',
  `name` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT 'name',
  `bank` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '银行',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `code` (`code`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=1636 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci COMMENT='码商提现';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `partner_summary`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `partner_summary` (
  `id` int NOT NULL AUTO_INCREMENT,
  `partner_id` int DEFAULT NULL,
  `formatted_date` date NOT NULL,
  `name` varchar(255) NOT NULL,
  `payoutCount` int DEFAULT '0',
  `payoutSum` decimal(18,4) DEFAULT '0.0000',
  `usdtCount` int DEFAULT '0',
  `usdtSum` decimal(18,4) DEFAULT '0.0000',
  `count` int DEFAULT '0',
  `sum` decimal(18,4) DEFAULT '0.0000',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `idx_partner_date` (`id`,`formatted_date`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=357 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='统计报表用';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `partner_tree`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `partner_tree` (
  `parent` int NOT NULL,
  `child` int NOT NULL,
  `distance` int NOT NULL,
  `id` int NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `partner_tree_parent_child_distance_key` (`parent`,`child`,`distance`) USING BTREE,
  KEY `partner_child_idx` (`child`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=39741 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci COMMENT='码商结构';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `partner_withdraw`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `partner_withdraw` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `code` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '订单号',
  `partner_id` int NOT NULL COMMENT '码商ID',
  `amount` decimal(12,2) NOT NULL COMMENT '订单金额',
  `amount_order` decimal(12,2) DEFAULT '0.00' COMMENT '处理金额',
  `amount_success` decimal(14,0) DEFAULT NULL COMMENT '出款成功金额',
  `admin_id` int DEFAULT NULL COMMENT '管理员ID',
  `status` int NOT NULL DEFAULT '0' COMMENT '订单状态 0待处理 1处理中 2已完成 -1已取消',
  `payment_codes` varchar(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '出款订单号',
  `time_success` datetime DEFAULT NULL COMMENT '成功时间',
  `time_updated` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `time_create` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '下单时间',
  `account` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '账号',
  `name` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '姓名',
  `ifsc` varchar(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT 'IFSC',
  `bank` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '银行',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=89 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci COMMENT='码商提现';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `payment`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `payment` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `bank_type` varchar(32) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '银行类型',
  `account_type` int DEFAULT NULL COMMENT '账户类型 0saving 1current 2corporate',
  `upi` varchar(500) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT 'UPI',
  `ifsc` varchar(32) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT 'ifsc',
  `account` varchar(32) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '账户',
  `name` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '姓名',
  `net_id` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '网银登录ID',
  `net_pw` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '网银登录密码',
  `net_trade_pw` varchar(32) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '网银交易密码',
  `phone` varchar(16) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '注册手机',
  `pin` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT '' COMMENT 'MPIN码',
  `tpin` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT '' COMMENT '交易的pin码',
  `gmail` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '谷歌邮箱',
  `gmail_pw` varchar(32) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '邮箱密码',
  `sys_balance` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '系统余额',
  `balance` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '余额',
  `partner_id` int NOT NULL COMMENT '所属码商',
  `certified` int NOT NULL DEFAULT '1' COMMENT '0未认证 1已认证',
  `status` int NOT NULL DEFAULT '0' COMMENT '0禁用 1启用',
  `time_create` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `amount_top` decimal(12,2) DEFAULT NULL COMMENT '单日上限',
  `manual_status` tinyint(1) NOT NULL DEFAULT '0' COMMENT '0 未锁定 1 二维码连续10单锁码，人工解锁',
  `bank_type_id` int NOT NULL DEFAULT '0',
  `priority_collection` int DEFAULT '0' COMMENT '0 普通收款 1 优先收款',
  `upi_list` varchar(500) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT 'upi列表',
  `bank_list` varchar(2000) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '银行列表',
  `weight` int DEFAULT '1' COMMENT '权重',
  `channel` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT '1001' COMMENT '通道号',
  `balance_limit` decimal(12,4) DEFAULT '0.0000' COMMENT '卡余额限制',
  `tpin_is_true` int DEFAULT '1' COMMENT 'tpin状态：0 不正确，1 正确',
  `time_update` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  `merchant_ids` longtext CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci COMMENT '商户列表设置用',
  `remarks` longtext CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci COMMENT '保存换upi或登出的错误消息',
  `fingerprint_path` longtext CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci COMMENT '指纹文件存储位置',
  `account_entire` longtext CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci COMMENT '账户完整列表',
  `account_selected` varchar(100) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '账户选中的',
  `account_enable` tinyint DEFAULT '0' COMMENT '0使用phone,1使用account',
  `account_accno` varchar(50) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '账户选中的accno',
  `account_iban` varchar(50) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '账户选中的iban',
  `wallet_status` tinyint NOT NULL DEFAULT '0' COMMENT '钱包状态：0不可用 1可用',
  `collection_status` tinyint NOT NULL DEFAULT '0' COMMENT '代收业务状态：0关闭 1开启',
  `payout_status` tinyint NOT NULL DEFAULT '0' COMMENT '代付业务状态：0关闭 1开启',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uk_payment_bank_phone` (`bank_type_id`,`phone`),
  KEY `partner_id` (`partner_id`) USING BTREE,
  KEY `accout` (`account`) USING BTREE,
  KEY `bank_type` (`bank_type`) USING BTREE,
  KEY `gmail` (`gmail`) USING BTREE,
  KEY `payment_bank_type_id` (`bank_type_id`) USING BTREE,
  KEY `phone` (`phone`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=533302 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci COMMENT='码商收款';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `payment_d`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `payment_d` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `bank_type` varchar(32) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '银行类型',
  `account_type` int DEFAULT NULL COMMENT '账户类型 0saving 1current 2corporate',
  `upi` varchar(500) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT 'UPI',
  `ifsc` varchar(32) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT 'ifsc',
  `account` varchar(32) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '账户',
  `name` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '姓名',
  `net_id` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '网银登录ID',
  `net_pw` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '网银登录密码',
  `net_trade_pw` varchar(32) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '网银交易密码',
  `phone` varchar(16) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '注册手机',
  `gmail` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '谷歌邮箱',
  `gmail_pw` varchar(32) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '邮箱密码',
  `sys_balance` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '系统余额',
  `balance` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '余额',
  `partner_id` int NOT NULL COMMENT '所属码商',
  `certified` int NOT NULL DEFAULT '0' COMMENT '0未认证 1已认证',
  `status` int NOT NULL DEFAULT '0' COMMENT '0禁用 1启用',
  `time_create` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `amount_top` decimal(12,2) DEFAULT NULL COMMENT '单日上限',
  `merchant_ids` longtext CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci COMMENT '商户列表设置用',
  `pin` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT 'MPIN码',
  `tpin` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '交易的pin码',
  `manual_status` tinyint(1) NOT NULL DEFAULT '0' COMMENT '0 未锁定 1 二维码连续10单锁码，人工解锁',
  `bank_type_id` int NOT NULL DEFAULT '0',
  `priority_collection` int DEFAULT '0' COMMENT '0 普通收款 1 优先收款',
  `upi_list` varchar(500) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT 'upi列表 ',
  `remarks` longtext CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci COMMENT '保存换upi或登出的错误消息',
  `fingerprint_path` longtext CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci COMMENT '指纹图路径',
  `account_entire` longtext CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci COMMENT '账户完整列表',
  `account_selected` varchar(100) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '账户选中项',
  `account_enable` tinyint DEFAULT '0' COMMENT '账户启用状态',
  `account_accno` varchar(50) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '账户选中的accno',
  `account_iban` varchar(50) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '账户选中的iban',
  `wallet_status` tinyint NOT NULL DEFAULT '0' COMMENT '钱包状态：0不可用 1可用',
  `collection_status` tinyint NOT NULL DEFAULT '0' COMMENT '代收业务状态：0关闭 1开启',
  `payout_status` tinyint NOT NULL DEFAULT '0' COMMENT '代付业务状态：0关闭 1开启',
  `bank_list` varchar(2000) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '银行列表',
  `weight` int DEFAULT '1' COMMENT '权重',
  `channel` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT '1001' COMMENT '通道号',
  `balance_limit` decimal(12,4) DEFAULT '0.0000' COMMENT '卡余额限制',
  `tpin_is_true` int DEFAULT '1' COMMENT 'tpin状态：0 不正确，1 正确',
  `time_update` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`) USING BTREE,
  KEY `account` (`account`) USING BTREE,
  KEY `partner_id` (`partner_id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=53292529 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci ROW_FORMAT=DYNAMIC COMMENT='码商收款-删';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `payment_upi_history`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `payment_upi_history` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `payment_id` int NOT NULL COMMENT 'payment.id',
  `partner_id` int NOT NULL COMMENT 'partner.id',
  `bank_id` int NOT NULL COMMENT 'bank_type.id',
  `upi` varchar(500) NOT NULL COMMENT 'upi',
  `time_create` datetime NOT NULL COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_payment_id_upi` (`payment_id`,`upi`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=106 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='payment UPI 变更历史';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `payment_weight`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `payment_weight` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `value` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '成功率百分比，或其他值',
  `weight` int DEFAULT '1' COMMENT '权重值',
  `payment_ids` longtext CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci COMMENT '所属的id集合，按逗号分开',
  `payment_numbers` int DEFAULT '0' COMMENT 'id数量',
  `type` int DEFAULT '0' COMMENT '0为按成功率，1为按是否新码，2为按是否优先收款',
  `time_updated` datetime DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=23 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci COMMENT='收款资料权重表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `permissions` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `pid` int NOT NULL COMMENT '父级ID',
  `name` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '指令权限名称',
  `path` varchar(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT 'API接口路径',
  `type` int NOT NULL DEFAULT '1' COMMENT '0页面权限 1指令权限',
  `status` int NOT NULL DEFAULT '1' COMMENT '0禁用 1正常',
  `level` tinyint(1) DEFAULT '1' COMMENT '级别编号',
  `admin_id` int DEFAULT '1' COMMENT '添加的管理员编号',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=202 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `phonepe`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `phonepe` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `pw` varchar(64) NOT NULL DEFAULT '123456' COMMENT '密码',
  `payment_id` int DEFAULT NULL COMMENT '码ID',
  `status` int NOT NULL DEFAULT '0' COMMENT '0 未连接 1已连接',
  `occupied` int NOT NULL DEFAULT '0' COMMENT '使用中',
  `time_create` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=1005 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `prize_earn_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `prize_earn_log` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'id',
  `user_id` int NOT NULL COMMENT '用户id',
  `user_name` varchar(50) NOT NULL COMMENT '用户名',
  `prize_id` int NOT NULL COMMENT '活动id',
  `prize_detail_id` int NOT NULL COMMENT '活动详情id',
  `prize_title` varchar(50) NOT NULL COMMENT '活动标题',
  `money` decimal(10,2) NOT NULL COMMENT '奖励金额',
  `remark` varchar(1024) DEFAULT NULL COMMENT '备注',
  `created_at` datetime NOT NULL COMMENT '创建日期',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=255 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='活动日志表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `prize_lottery_chance`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `prize_lottery_chance` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID, 主键',
  `user_id` int NOT NULL COMMENT '用户id',
  `chance_num` int DEFAULT NULL COMMENT '抽奖机会数量',
  `created_at` datetime NOT NULL COMMENT '创建日期',
  `updated_at` datetime NOT NULL COMMENT '修改时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=17 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='活动-用户抽奖机会表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `prize_lottery_chance_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `prize_lottery_chance_log` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'id',
  `user_id` int NOT NULL COMMENT '用户id',
  `prize_id` int DEFAULT NULL COMMENT '活动id',
  `before_num` int NOT NULL COMMENT '变动前数量',
  `num` int NOT NULL COMMENT '变动机会次数',
  `after_num` int NOT NULL COMMENT '变动后数量',
  `remark` varchar(2000) DEFAULT NULL COMMENT '备注',
  `created_at` datetime NOT NULL COMMENT '创建日期',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=334 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='活动-用户机会变动记录';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `prize_partner_beginner_tutorial_task_progress`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `prize_partner_beginner_tutorial_task_progress` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `prize_id` int NOT NULL COMMENT '活动设置ID，即prize_setting.id',
  `partner_id` int NOT NULL COMMENT '码商ID',
  `top_parent_id` int DEFAULT NULL COMMENT '顶商ID',
  `pid` int DEFAULT NULL COMMENT 'ID',
  `is_finished` tinyint(1) NOT NULL DEFAULT '0' COMMENT '任务是否完成;0=否,1=是',
  `is_awarded` tinyint(1) NOT NULL DEFAULT '0' COMMENT '是否已经发放奖励;0=否,1=是',
  `prize_amount` decimal(10,2) DEFAULT NULL COMMENT '实际奖励额度',
  `time_awarded` datetime DEFAULT NULL COMMENT '奖励发放时间',
  `time_register` datetime DEFAULT NULL COMMENT '码商的注册时间（设定支付安全码）',
  `time_set_trade_hash` datetime DEFAULT NULL COMMENT '设定支付安全码的时间',
  `time_watch_tutorial_videos` datetime DEFAULT NULL COMMENT '码商观看新手教程视频的时间',
  `time_bind_upi` datetime DEFAULT NULL COMMENT '关联upi的时间',
  `time_order_success` datetime DEFAULT NULL COMMENT '完成一笔订单购买的时间',
  `create_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uk_prize_id_partner_id` (`prize_id`,`partner_id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=7132 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='活动-码商-参加新手活动结果记录';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `prize_pool`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `prize_pool` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID, 主键',
  `pool_amount` decimal(14,4) NOT NULL COMMENT '奖池金额',
  `created_at` datetime NOT NULL COMMENT '创建日期',
  `updated_at` datetime NOT NULL COMMENT '修改时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='活动-奖池';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `prize_pool_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `prize_pool_log` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'id',
  `code` varchar(32) NOT NULL COMMENT '流水号',
  `record_type` int NOT NULL COMMENT '流水类型  1 奖池增加  2 奖励发放',
  `change_before` decimal(14,4) NOT NULL COMMENT '账变前金额',
  `amount` decimal(14,4) NOT NULL COMMENT '账变金额',
  `change_after` decimal(14,4) NOT NULL COMMENT '账变后金额',
  `user_type` int DEFAULT NULL COMMENT '交易用户类型  0码商 1商户',
  `user_id` int DEFAULT NULL COMMENT '交易用户ID',
  `remark` varchar(2000) DEFAULT NULL COMMENT '备注',
  `created_at` datetime NOT NULL COMMENT '创建日期',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=406 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='活动-奖池变动记录';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `prize_setting`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `prize_setting` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '活动ID, 主键',
  `title` varchar(255) NOT NULL COMMENT '标题',
  `content` text COMMENT '内容',
  `type` tinyint(1) DEFAULT NULL COMMENT '活动类型，0 抽奖，1 金额满赠，2 单数满赠，3 新手活动',
  `participant` varchar(4096) DEFAULT NULL COMMENT '参与人员id；-1全部人员，指定人员：id使用逗号隔开',
  `pic` varchar(255) DEFAULT NULL COMMENT '图片路径',
  `created_at` datetime NOT NULL COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `status` tinyint(1) NOT NULL DEFAULT '1' COMMENT '0:禁用, 1:启用',
  `is_app_show` tinyint(1) DEFAULT '0' COMMENT '是否在app显示，0:不显示, 1:显示',
  `begin_at` datetime NOT NULL COMMENT '起始时间',
  `end_at` datetime NOT NULL COMMENT '结束时间',
  `lottery_chance_setting` int DEFAULT NULL COMMENT '抽奖机会设置(几个订单获取一次抽奖机会，仅抽奖使用)',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=65677 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='活动设置表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `prize_setting_detail`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `prize_setting_detail` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '奖励ID, 主键',
  `prize_id` int NOT NULL COMMENT '活动ID, 外键',
  `prize_title` varchar(255) NOT NULL COMMENT '活动标题',
  `title` varchar(255) NOT NULL COMMENT '奖励标题',
  `prize_limit_min` int DEFAULT NULL COMMENT '活动触发下限',
  `prize_limit_max` int DEFAULT NULL COMMENT '活动触发上限',
  `prize_type` tinyint(1) DEFAULT NULL COMMENT '奖励类型：1. 固定奖励 2 奖金池比例奖励 3 幸运奖',
  `money` decimal(10,2) NOT NULL DEFAULT '0.00' COMMENT '奖励金额',
  `ratio` decimal(10,6) DEFAULT NULL,
  `created_at` datetime NOT NULL COMMENT '创建时间',
  `updated_at` datetime NOT NULL COMMENT '更新时间',
  `status` tinyint(1) NOT NULL DEFAULT '1' COMMENT '0:禁用, 1:启用',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=45 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='活动设置明细表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `prize_setting_partner_beginner_tutorial_task`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `prize_setting_partner_beginner_tutorial_task` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '任务ID',
  `prize_id` int NOT NULL COMMENT '活动设置ID，即prize_setting.id',
  `name` varchar(255) DEFAULT NULL COMMENT '任务名称',
  `type` tinyint DEFAULT NULL COMMENT '任务类型;1=set_trade_hash(设定支付安全码),2=watch_tutorial_videos(观看引导视频),3=bind_upi(绑定UPI),4=order_success(成功代付订单)',
  `status_enable` tinyint DEFAULT '0' COMMENT '是否启用;0=否,1=是',
  `description` longtext COMMENT '任务说明',
  `json_parameters` varchar(5000) DEFAULT NULL COMMENT '自定义参数',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime DEFAULT NULL COMMENT '修改时间',
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_prize_id` (`prize_id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='活动设置表-新手引导任务';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `robot_merchant`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `robot_merchant` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `merchant_id` int DEFAULT '0',
  `user_name` varchar(255) DEFAULT NULL COMMENT '小飞机联系方式',
  `chat_id` varchar(20) NOT NULL COMMENT '群组id',
  `chat_title` varchar(255) NOT NULL COMMENT '群title',
  `robot_name` varchar(64) DEFAULT NULL COMMENT '机器人名称',
  `robot_token` varchar(64) DEFAULT NULL COMMENT '机器人Token',
  `remark` varchar(255) DEFAULT NULL COMMENT '备注',
  `create_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '添加时间',
  `update_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` tinyint(1) DEFAULT '0' COMMENT '删除',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='商户消息设置表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `robot_message`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `robot_message` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT '消息',
  `type` varchar(20) DEFAULT NULL COMMENT '发送类型',
  `enabled` tinyint(1) DEFAULT '0' COMMENT '是否启用',
  `status` varchar(20) DEFAULT NULL COMMENT '发送状态',
  `send_time` datetime DEFAULT NULL COMMENT '发送时间',
  `subscribers` text,
  `time_create` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `time_update` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `creator` int DEFAULT NULL COMMENT '创建人',
  `updater` int DEFAULT NULL COMMENT '更新人',
  `deleted` tinyint(1) DEFAULT '0' COMMENT '是否删除',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `robot_message_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `robot_message_log` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `mid` bigint NOT NULL COMMENT '消息ID',
  `sid` bigint NOT NULL COMMENT '订阅者ID',
  `chat_id` varchar(20) DEFAULT NULL COMMENT '会话ID',
  `chat_name` varchar(64) DEFAULT NULL COMMENT '会话名称',
  `content` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT '消息内容',
  `robot_token` varchar(64) DEFAULT NULL COMMENT '机器人token',
  `robot_name` varchar(64) DEFAULT NULL COMMENT '机器人名称',
  `success` tinyint(1) DEFAULT NULL COMMENT '是否成功',
  `remark` text COMMENT '原因备注',
  `time_create` datetime DEFAULT NULL COMMENT '日志时间',
  `mchid` bigint DEFAULT NULL COMMENT '商户ID',
  `nick_name` varchar(255) DEFAULT NULL COMMENT '商户昵称',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=53 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='机器人消息日志';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `robot_message_subscriber`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `robot_message_subscriber` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `mid` bigint DEFAULT NULL COMMENT '消息ID',
  `associated_id` bigint DEFAULT NULL COMMENT '关联ID',
  `status` varchar(20) DEFAULT NULL COMMENT '发送状态',
  `time_create` datetime DEFAULT NULL COMMENT '创建时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='机器人消息订阅者';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `roles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `roles` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `parent_id` int NOT NULL DEFAULT '1' COMMENT '父角色ID',
  `key_name` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '角色标识',
  `name` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '角色名称',
  `permissions` varchar(2048) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci DEFAULT NULL COMMENT '指令权限',
  `description` varchar(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '备注说明',
  `time_update` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间 ',
  `time_create` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `encryption` tinyint(1) NOT NULL DEFAULT '0' COMMENT '0不加密1加密',
  `level` tinyint(1) DEFAULT '1' COMMENT '级别编号',
  `admin_id` int DEFAULT '1' COMMENT '添加的管理员编号',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=41 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci COMMENT='角色';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `sms_record`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sms_record` (
  `id` int NOT NULL AUTO_INCREMENT,
  `frm` varchar(45) DEFAULT NULL COMMENT '短信号码',
  `content` varchar(450) DEFAULT NULL COMMENT '短信内容',
  `payment_id` int DEFAULT NULL COMMENT '银行卡ID',
  `status` int DEFAULT '0' COMMENT '是否解析成功',
  `remark` varchar(100) DEFAULT NULL COMMENT '备注',
  `received_time` datetime DEFAULT NULL COMMENT '短信接收时间',
  `created` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `id_UNIQUE` (`id`) USING BTREE,
  KEY `frm` (`frm`) USING BTREE,
  KEY `payment_id` (`payment_id`) USING BTREE,
  KEY `created` (`created`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=10252 DEFAULT CHARSET=utf8mb3 ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `statistics_daily_merchant_orders_df`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `statistics_daily_merchant_orders_df` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '自增ID',
  `merchant_id` int NOT NULL COMMENT '商户ID',
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
  UNIQUE KEY `uk_stats_date` (`merchant_id`,`stats_date`) USING BTREE COMMENT '统计日期唯一索引'
) ENGINE=InnoDB AUTO_INCREMENT=35756 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='代付订单每日统计表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `statistics_daily_merchant_orders_ds`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `statistics_daily_merchant_orders_ds` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '自增ID',
  `merchant_id` int NOT NULL COMMENT '商户ID',
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
  UNIQUE KEY `uk_stats_date` (`merchant_id`,`stats_date`) USING BTREE COMMENT '统计日期唯一索引'
) ENGINE=InnoDB AUTO_INCREMENT=35756 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='代收订单每日统计表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `statistics_daily_partner_orders_df`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
) ENGINE=InnoDB AUTO_INCREMENT=140268 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='代付订单每日统计表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `statistics_daily_partner_orders_ds`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
) ENGINE=InnoDB AUTO_INCREMENT=140289 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='代收订单每日统计表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `sys_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_info` (
  `id` int NOT NULL COMMENT 'ID',
  `status_payment_service` tinyint(1) NOT NULL COMMENT '系统代收代付总开关',
  `status_jazzcash_payout_service` tinyint(1) NOT NULL COMMENT 'JazzCash代付单独控制开关',
  `sys_ip_w` longtext CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci COMMENT '系统IP白名单',
  `api_ip_b` longtext CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci COMMENT '接口IP黑名单',
  `bulletin` varchar(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT 'APP公告',
  `telegram` varchar(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT 'telegram客服',
  `rate_df` decimal(14,4) DEFAULT NULL COMMENT '代付费率',
  `status_df` tinyint(1) NOT NULL DEFAULT '0' COMMENT '0停止1开启',
  `expired_status_df` tinyint unsigned NOT NULL DEFAULT '1' COMMENT '代付过期开关0停止1开启',
  `usdt_exchange_rate` decimal(12,4) NOT NULL DEFAULT '0.0000' COMMENT 'usdt费率',
  `usdt_exchange_status` tinyint(1) NOT NULL DEFAULT '0' COMMENT 'usdt开关0停止1开启',
  `usdt_exchange_bonus_rate` decimal(12,4) NOT NULL DEFAULT '0.0000' COMMENT '红利比例',
  `app_info` json DEFAULT NULL COMMENT 'app更新信息',
  `range_df` json DEFAULT NULL COMMENT '设定转三方支付代收金额范围',
  `range_ds` json DEFAULT NULL COMMENT '设定转三方支付代收金额范围',
  `usdt_received_address` longtext CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci COMMENT 'usdt转入地址',
  `usdt_amount_limit` decimal(12,4) DEFAULT '0.0000' COMMENT 'usdt金额限制',
  `merchant_ids` varchar(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '商户编号一栏 逗号分隔',
  `range_usdt_df` json DEFAULT NULL,
  `payment_ids` varchar(2000) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '加码接单',
  `dsdf_lock` json DEFAULT NULL COMMENT '代收代付锁定设置',
  `negative_limit` decimal(14,2) NOT NULL DEFAULT '0.00' COMMENT '码商欠额上限(负数)',
  `tier_rate_config` json DEFAULT NULL COMMENT '层级费率配置',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci COMMENT='系统信息';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `sys_operation_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_operation_log` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `uid` bigint DEFAULT NULL COMMENT '用户ID',
  `biz_id` bigint DEFAULT NULL COMMENT '数据模块ID',
  `utype` varchar(20) DEFAULT NULL COMMENT '用户类型',
  `user_ip` varchar(50) DEFAULT NULL COMMENT '用户ip',
  `request_path` varchar(255) DEFAULT NULL COMMENT '请求路径',
  `module` varchar(64) DEFAULT NULL COMMENT '模块',
  `event_type` varchar(64) DEFAULT NULL COMMENT '操作类型',
  `event_desc` varchar(255) DEFAULT NULL COMMENT '操作描述',
  `event_content` varchar(2000) DEFAULT NULL COMMENT '操作内容',
  `event_result` varchar(45) DEFAULT NULL COMMENT '操作结果',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=205 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='操作日志';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `sys_payment`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_payment` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `account` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '账号',
  `name` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '姓名',
  `type` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL DEFAULT '1' COMMENT '类型 默认1 bank',
  `bank` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '银行名称',
  `ifsc` varchar(32) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT 'ifsc',
  `admin_id` int NOT NULL COMMENT '操作管理ID',
  `status` int NOT NULL DEFAULT '1' COMMENT '0禁用 1正常',
  `time_update` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间 ',
  `time_create` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `account` (`account`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=38 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci COMMENT='系统收款';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `sys_record`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_record` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `code` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '流水号',
  `amount` decimal(14,4) NOT NULL COMMENT '帐变金额',
  `record_type` int NOT NULL DEFAULT '0' COMMENT '流水类型 0手动 1码商充值 2商户充值 3码商提现 4商户提现',
  `admin_id` int DEFAULT NULL COMMENT '操作员ID',
  `remark` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '备注',
  `time_create` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `name` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '姓名',
  `account` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '账号',
  `type` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '类型',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci COMMENT='系统流水';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `sys_settings`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_settings` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(50) DEFAULT NULL COMMENT '键名称',
  `value` text CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci COMMENT '键内容',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='系统配置表(报表定义等)';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `text_materials`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `text_materials` (
  `id` int NOT NULL AUTO_INCREMENT,
  `genre` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `title` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `content` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `material_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'ospay',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `third_pay_df`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `third_pay_df` (
  `id` int NOT NULL AUTO_INCREMENT,
  `mer_id` varchar(45) DEFAULT NULL,
  `mer_key` varchar(450) DEFAULT NULL,
  `pay_url` varchar(450) DEFAULT NULL,
  `pay_name` varchar(45) DEFAULT NULL,
  `pay_name_zh` varchar(45) DEFAULT NULL COMMENT '支付方中文名',
  `channel_code` int DEFAULT NULL COMMENT '网关如901902等',
  `is_self` int DEFAULT '0' COMMENT '供应链是否是自身，默认0不是',
  `is_xiaoshu` int DEFAULT '0' COMMENT '带不带小数，默认0不带\n',
  `notify_ip` varchar(256) DEFAULT NULL COMMENT '回调通知的ip',
  `query_url` varchar(450) DEFAULT NULL COMMENT '查询订单url',
  `status` tinyint DEFAULT NULL,
  `mer_key2` varchar(450) DEFAULT NULL COMMENT '可以放公钥',
  `mer_key3` varchar(2000) DEFAULT NULL COMMENT '可以放私钥',
  `mer_key4` varchar(450) DEFAULT NULL COMMENT '放其他参数',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=109 DEFAULT CHARSET=utf8mb3 ROW_FORMAT=DYNAMIC COMMENT='第三方代付';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `transfer`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `transfer` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `code` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '订单号',
  `partner_id` int NOT NULL COMMENT 'ID',
  `to_partner_id` int NOT NULL COMMENT '要转入的ID',
  `amount` decimal(12,2) NOT NULL COMMENT '订单金额',
  `admin_id` int DEFAULT NULL COMMENT '管理员ID',
  `status` int NOT NULL DEFAULT '1' COMMENT '订单状态 0待处理 1处理中 2已完成 -1已取消',
  `time_success` datetime DEFAULT NULL COMMENT '成功时间',
  `time_updated` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `time_create` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '下单时间',
  `type` int NOT NULL DEFAULT '1' COMMENT '类型 1码商互转',
  `remark` varchar(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT '备注',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `code` (`code`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=17769 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci COMMENT='转账表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `usdt_deposit_orders`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `usdt_deposit_orders` (
  `id` int NOT NULL AUTO_INCREMENT,
  `serial_number` varchar(64) CHARACTER SET utf8mb3 COLLATE utf8mb3_unicode_ci NOT NULL COMMENT '序列号',
  `status` int NOT NULL DEFAULT '0' COMMENT '订单状态 0待处理 1处理中(拿到地址) 2已完成(已支付) -1已取消',
  `usdt_amount` decimal(12,4) DEFAULT NULL COMMENT 'USDT',
  `exchange_rate` decimal(8,4) DEFAULT NULL COMMENT '汇率',
  `currency_amount` decimal(12,4) DEFAULT NULL COMMENT '卢比数额',
  `block_chain` varchar(64) DEFAULT NULL COMMENT '区块链',
  `bonus_rate` decimal(6,4) DEFAULT NULL COMMENT '红利比例',
  `bonus` decimal(10,4) DEFAULT NULL COMMENT '红利',
  `total_amount` decimal(12,4) DEFAULT NULL COMMENT '上分总数',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '订单生成时间',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最後更新时间',
  `paid_at` datetime DEFAULT NULL COMMENT '支付时间',
  `request_at` datetime DEFAULT NULL COMMENT '请求订单时间',
  `address` varchar(255) DEFAULT NULL COMMENT '收款地址',
  `user_id` int NOT NULL COMMENT 'partner id',
  `admin_id` int DEFAULT NULL COMMENT 'admin id',
  `receipt_image` tinyint(1) DEFAULT '0' COMMENT '是否上传图片',
  `remark` varchar(255) DEFAULT NULL COMMENT '註解',
  `txid` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `serial_number` (`serial_number`) USING BTREE,
  KEY `user_id` (`user_id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=1176 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `user_message`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `user_message` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `msg_id` bigint NOT NULL COMMENT '消息ID',
  `user_id` int NOT NULL COMMENT '用户ID',
  `status` tinyint NOT NULL DEFAULT '0' COMMENT '状态:0未读 1已读 -1已删除',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_msg_user` (`msg_id`,`user_id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_status` (`status`)
) ENGINE=InnoDB AUTO_INCREMENT=138 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户消息关系表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `vip`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `vip` (
  `vip` int NOT NULL COMMENT '等级',
  `conditions` decimal(12,2) NOT NULL COMMENT '条件',
  `ds_min` decimal(12,2) NOT NULL COMMENT '代收最小限额',
  `ds_max` decimal(12,2) NOT NULL COMMENT '代收最大限额',
  `df_min` decimal(12,2) NOT NULL COMMENT '代付最小限额',
  `df_max` decimal(12,2) NOT NULL COMMENT '代付最大限额',
  `top_card` int NOT NULL DEFAULT '1' COMMENT '默认激活卡数',
  `deposit_ratio` tinyint(1) NOT NULL DEFAULT '20' COMMENT '押金比例',
  PRIMARY KEY (`vip`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;
