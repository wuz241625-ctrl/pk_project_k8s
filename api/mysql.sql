-- JAZZCASH 银行类型
INSERT INTO `bank_type` (`id`, `name`, `url`, `type`, `status`, `logo_url`) VALUES (98, 'JAZZCASH', NULL, 1, 1, NULL);

-- refs-486 start ----------------------------------------
-- 2025-10-06 - hins

ALTER TABLE `merchant`
  ALGORITHM=INPLACE,
  LOCK=NONE,
  ADD COLUMN `amount_fixed_max` DECIMAL(10, 2)
  COMMENT '代付单笔最大额度';

-- refs-486 end ----------------------------------------

-- 2025-10-01 10601    拆分四个类别
-- 添加银行类型不匹配错误码
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('10307','payment','warning','银行类型不匹配，只支持AMAZON银行','银行类型不支持','当前操作只支持AMAZON银行','请使用AMAZON银行类型的账户','Bank Type Not Supported','This operation only supports AMAZON bank.',NULL,NULL,NULL,NULL,'2025-05-08 14:30:20','2025-05-08 14:30:20');

-- 添加SMS验证超时错误码
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('10308','payment','warning','SMS验证超时，请在30秒内完成短信验证','SMS验证超时','短信验证超时，请重新发送验证码','请重新获取验证码并在30秒内完成验证','SMS Timeout','SMS verification timeout. Please try again.',NULL,NULL,NULL,NULL,'2025-01-15 14:30:35','2025-01-15 14:30:35');

-- 添加操作频繁错误码
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('10606','business','warning','操作过于频繁','操作过于频繁','您的操作过于频繁，请稍后再试','请等待一段时间后再进行操作','Too Frequent','Operation too frequent. Please try again later.',NULL,NULL,NULL,NULL,'2025-05-08 14:30:15','2025-05-08 14:30:15');

-- 添加Redis操作失败错误码
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('10902','system','error','Redis操作失败，系统错误','Redis操作失败','系统缓存操作失败','请稍后重试，如问题持续请联系客服','Redis Error','Redis operation failed. Please try again.',NULL,NULL,NULL,NULL,'2025-01-15 14:30:40','2025-01-15 14:30:40');


-- ============================================
-- EasyPaisa 明细账单功能权限配置
-- 在余额流水下增加一个"明细账单"菜单
-- 创建时间: 2025-09-23
-- ============================================

-- 在余额流水下添加"明细账单"菜单 
INSERT INTO `permissions` (`id`, `pid`, `name`, `path`, `type`, `status`, `level`, `admin_id`) VALUES 
(201, 93, '明细账单', '/record/easypaisa-bills', 0, 1, 2, 1);

-- 为管理员角色(ID=1)添加这个权限
UPDATE `roles` SET 
`permissions` = CONCAT(
    COALESCE(permissions, ''), 
    CASE 
        WHEN permissions IS NULL OR permissions = '' THEN '201'
        ELSE ',201'
    END
) 
WHERE `id` = 1;

-- ============================================
=======
-- 2025-9-23 统计二维码下载次数
ALTER TABLE orders_ds 
ADD COLUMN count_statics varchar(255) NULL COMMENT '统计次数json格式';

-- 2025-9-20 通道是否显示二维码
ALTER TABLE `channel` 
ADD COLUMN `is_show_qr` tinyint(1) NULL DEFAULT 0 COMMENT '0/1 是否显示二维码   不显示/显示';

-- 创建IFSC字段扩容
ALTER TABLE bank_ifsc MODIFY COLUMN IFSC varchar(50);

INSERT INTO bank_ifsc (BANK, IFSC, BRANCH, CENTRE, DISTRICT, STATE, ADDRESS, CONTACT, IMPS, RTGS, CITY, ISO3166, NEFT, MICR, UPI, SWIFT) VALUES
('Allied Bank Limited', 'ABPAPKKA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, 'ABPAPKKA'),
('Askari Commercial Bank Limited', 'ASCMPKKA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, 'ASCMPKKA'),
('Al Baraka Islamic Bank Limited', 'AIINPKKA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, 'AIINPKKA'),
('Advans Microfinance Bank', 'AdvansMicrofinanceBank', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('Apna Microfinance Bank', 'APNAPKKA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, 'APNAPKKA'),
('Alfa Pay', 'AlfaPay', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('Bank AlFalah Limited', 'ALFHPKKA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, 'ALFHPKKA'),
('Bank Al Habib Limited', 'BAHLPKKA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, 'BAHLPKKA'),
('Burj Bank Limited', 'BurjBankLimited', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('Bank Islami Pakistan Limited', 'BKIPPKKA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, 'BKIPPKKA'),
('Bank Makramah Limited BML', 'BankMakramahLimitedBML', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('Bank of Khyber', 'KHYBPKKA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, 'KHYBPKKA'),
('Bank Of Punjab', 'BankOfPunjab', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('CDNS', 'CDNS', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('Citi Bank', 'CitiBank', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('Dubai Islamic Bank', 'DubaiIslamicBank', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('Digitt', 'Digitt', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('Faysal Bank Limited', 'FAYSPKKA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, 'FAYSPKKA'),
('FINCA', 'FINCA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('First Women Bank', 'FirstWomenBank', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('Finja', 'Finja', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('Habib Bank Limited HBL', 'HABBPKKARTG', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, 'HABBPKKARTG'),
('HBL Konnect', 'HBLKonnect', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('HBL Microfinance Bank', 'HBLMicrofinanceBank', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('FirstPay', 'FirstPay', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('Habib Metropolitan Bank', 'MPBLPKKA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, 'MPBLPKKA'),
('Hubpay', 'HUBPPKKA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, 'HUBPPKKA'),
('ICBC', 'ICBC', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('JazzCash', 'JazzCash', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('JS Bank', 'JSBLPKKA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, 'JSBLPKKA'),
('KASB Bank', 'KASBBank', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('KEENU', 'KEENU', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('Khushhali Microfinance Bank KMBL', 'KHBLDFID', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, 'KHBLDFID'),
('Mashreq Bank Pakistan Limited', 'MashreqBankPakistanLimited', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('MCB Bank Limited', 'MUCBPKKKRTG', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, 'MUCBPKKKRTG'),
('Meezan Bank', 'MEZNPKKA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, 'MEZNPKKA'),
('MCB Islamic Bank', 'MCBIslamicBank', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('Mobilink Microfinance Bank', 'JCICPKKA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, 'JCICPKKA'),
('National Bank of Pakistan', 'NBPBPKKA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, 'NBPBPKKA'),
('NIB Bank', 'NIBBank', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('NayaPay', 'NAYAPKKA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, 'NAYAPKKA'),
('NRSP Bank Fori Cash', 'NRSPBankForiCash', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('OneZapp', 'OneZapp', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('Paymax', 'Paymax', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('Raqami Islamic Digital Bank', 'RQMIPKKA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, 'RQMIPKKA'),
('Samba Bank', 'SambaBank', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('Soneri Bank Limited', 'SoneriBankLimited', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('Standard Chartered Bank', 'SCBLPKKA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, 'SCBLPKKA'),
('Silk Bank', 'SilkBank', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('Sindh Bank', 'SindhBank', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('SimSim', 'SimSim', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('U Microfinance Bank', 'UMicrofinanceBank', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('United Bank Limited UBL', 'UNILPKKARTG', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, 'UNILPKKARTG'),
('Upaisa', 'Upaisa', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('YAP', 'YAPPKKA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, 'YAPPKKA'),
('ZTBL', 'ZTBL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL),
('SadaPay', 'SADAPKKA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, 'SADAPKKA'),
('EasyPaisa', 'EasyPaisa', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'PK', NULL, NULL, NULL, NULL);

-- 创建EasyPaisa操作日志表
CREATE TABLE IF NOT EXISTS `easypaisa_operation_logs` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '日志ID',
  
  --  转出方信息
  `from_payment_id` varchar(50) DEFAULT NULL COMMENT '转出方payment_id',  
  `from_account_number` varchar(50) DEFAULT NULL COMMENT '转出方EasyPaisa手机号',
  
  -- 转入方信息  
  `to_account_number` varchar(100) DEFAULT NULL COMMENT '转入账号(手机号或银行卡号)',
  `to_account_name` varchar(100) DEFAULT NULL COMMENT '收款人姓名',
  `to_bank_code` varchar(50) DEFAULT NULL COMMENT '银行代码(IFSC等)',
  `to_bank_name` varchar(100) DEFAULT NULL COMMENT '银行名称',
  
  -- 业务信息
  `order_code` varchar(100) DEFAULT NULL COMMENT '关联订单号',
  `operation_type` varchar(50) NOT NULL COMMENT '操作类型：login,logout,transfer_same_bank,transfer_cross_bank,balance_check等',
  `transfer_type` varchar(50) DEFAULT NULL COMMENT '转账类型：EasyPaisa同行转账,跨行转账到银行卡',
  `amount` decimal(12,2) DEFAULT NULL COMMENT '操作金额',
  `currency` varchar(10) DEFAULT 'PKR' COMMENT '货币类型',
  
  -- 交易结果
  `transaction_id` varchar(100) DEFAULT NULL COMMENT 'EasyPaisa交易ID',
  `reference_number` varchar(100) DEFAULT NULL COMMENT '参考号',
  `status` varchar(20) NOT NULL COMMENT '操作状态：success,failed,pending',
  
  -- 余额信息  
  `before_balance` decimal(12,2) DEFAULT NULL COMMENT '操作前余额',
  `after_balance` decimal(12,2) DEFAULT NULL COMMENT '操作后余额',
  
  -- 技术信息
  `api_request` text COMMENT 'API请求数据(JSON)',
  `api_response` text COMMENT 'API响应数据(JSON)', 
  `api_endpoint` varchar(200) DEFAULT NULL COMMENT 'API端点路径',
  `request_uuid` varchar(50) DEFAULT NULL COMMENT '请求UUID',
  `error_code` varchar(20) DEFAULT NULL COMMENT '错误代码',
  `error_message` text COMMENT '错误信息',
  `process_time` int(11) DEFAULT NULL COMMENT '处理耗时（毫秒）',
  `retry_count` int(11) DEFAULT 0 COMMENT '重试次数',
  
  -- 系统信息
  `ip_address` varchar(45) DEFAULT NULL COMMENT '服务器IP地址',
  `user_agent` varchar(500) DEFAULT NULL COMMENT '用户代理',
  `server_process_id` int(11) DEFAULT NULL COMMENT '处理进程ID', 
  `trace_id` varchar(50) DEFAULT NULL COMMENT '链路追踪ID',
  `process_log` TEXT COMMENT '完整流程日志(JSON格式)',
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
  
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='EasyPaisa操作日志表';


-- 2025-8-17 orders_ds 追加 tax
ALTER TABLE `orders_ds` 
ADD COLUMN `tax` decimal(10, 4) NULL DEFAULT 0.0000 COMMENT '税费';
INSERT INTO `otherpay`(`merchant_id`, `key`, `key2`, `key3`, `name`, `pay_url`, `channel_code`, `notify_ip`, `query_url`, `forcible`, `status`, `updated`, `created`) VALUES ('pakistanpay', '542c5b9767a240d88ad8f25fa83c4c95', '', '', 'pakistanpay', 'http://104.198.86.150:83', NULL, '', '', 0, 1, '2025-08-18 00:52:25', '2025-04-02 16:39:21');
ALTER TABLE `orders_ds`
ADD COLUMN `trans_id` varchar(128) COLLATE utf8_unicode_ci DEFAULT NULL COMMENT '交易ID';

ALTER TABLE `orders_ds`
ADD INDEX `trans_id` (`trans_id`) USING BTREE;

ALTER TABLE `bank_record`
ADD COLUMN `trans_id` varchar(128) DEFAULT NULL COMMENT '交易ID';

ALTER TABLE `bank_record`
ADD INDEX `trans_id` (`trans_id`) USING BTREE;


-- ===========================================
-- 添加orders_df表代付类型字段 (2025-08-22)
-- ===========================================

-- 为orders_df表添加代付类型字段
ALTER TABLE `orders_df` 
ADD COLUMN `payout_type` TINYINT(1) NOT NULL DEFAULT 0 
COMMENT '代付类型: 0=手动代付, 1=自动代付, 2=第三方代付' 
AFTER `otherpay_code`;
-- 为orders_df表添加重试次数字段
ALTER TABLE `orders_df` 
ADD COLUMN `retry_count` INT(11) NOT NULL DEFAULT 0 
COMMENT '重试次数: 记录代付订单的重试次数';

-- ===========================================
-- 自动代付订单监控权限配置 (2025-08-21)
-- ===========================================

-- 添加自动代付订单监控权限
INSERT IGNORE INTO permissions (pid, name, path, type, status, level, admin_id) 
VALUES (0, '自动代付订单监控', '/AutoDfddMonitor', 0, 1, 1, 1);

-- 为管理员角色添加自动代付订单监控权限
-- 注意：此处使用CONCAT追加权限ID 196，不会覆盖现有权限
UPDATE roles SET permissions = CONCAT(permissions, ',196') WHERE id = 1 AND FIND_IN_SET('196', permissions) = 0;

-- ===========================================
-- 2025-8-4 usdt_deposit_orders 回调追加 txid
ALTER TABLE `usdt_deposit_orders`
ADD COLUMN `txid` varchar(255) DEFAULT NULL;

-- refs-382 start ----------------------------------------
-- 2025-07-29 - hins

-- 查出 “代付拆单” 的父节点ID
SELECT pid INTO @pid FROM `permissions` WHERE `name` = '代付拆单' LIMIT 1;

-- 插入 “代付拆单回退” 的权限
INSERT INTO `permissions` (`pid`, `name`, `path`, `type`, `status`, `level`, `admin_id`)
VALUES (@pid, '代付拆单回退', '/order/handleOrderdfRevert', 1, 1, 2, 1);

-- 修复 路由
update `permissions` SET `path` = '/order/getOrderDfSplit' WHERE `name` = '代付子单查看';
update `permissions` SET `path` = '/order/confirmSplitOrder' WHERE `name` = '代付拆单';

-- refs-382 end ----------------------------------------

-- 2025-7-22 mars代付开发
INSERT INTO `third_pay_df`(`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`,
 `is_xiaoshu`, `notify_ip`, `query_url`, `status`, `mer_key2`, `mer_key3`, `mer_key4`) VALUES 
 ('marspay', 'dXGck7syJVGVy5jYIJ4G7kBSY1fX9QHjRhUuHM6Zv5cYBLF6wkK6hEsC9zND', 'https://mars-pay.in/api/payout/v1/transfer-now', 'marspay', 'marspay代付', NULL, 0, 0, '13.233.1.148', 'https://mars-pay.in/api/telecom/v1/check-status', 1, NULL, NULL, NULL);

-- 2025-7-16 更新错误码类型：将warning改为error
UPDATE `error_messages` SET `severity` = 'error' WHERE `error_code` IN ('20101', '20102', '20103', '20104');

--2025-7-12 kaven #345 分批 统计 可接单码商 按照余额阶梯显示
-- 插入条件数据
INSERT INTO `sys_settings` (`name`, `value`)
VALUES ('partner_balance_statistics', '{"bound":"500,2000,5000,10000,20000,50000,100000","num":"145","data_select":"0,1,3,6,12,24","interval_time":"10"}');
-- 添加码商余额统计页面权限
INSERT INTO `permissions` (`pid`, `name`, `path`, `type`, `status`, `level`, `admin_id`) VALUES (0, '码商余额统计', '', 0, 1, 2, 1);
-- end #345 分批 统计 可接单码商 按照余额阶梯显示

--2025-7-12 增加indus协议改造的报错信息
-- ===========================================
-- HTTP Login Controller 错误码 (10xxx)
-- ===========================================

-- HTTP认证相关错误
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('10211','system','warning','Bearer token error, API error','认证失败','登录令牌无效或已过期','请重新登录系统','Authentication Failed','Bearer token error, please sign in','Please sign in again',NULL,NULL,NULL,NOW(),NOW());

-- 银行类型支持错误
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('10212','system','warning','Unsupported bank type','银行类型不支持','当前不支持该银行类型','请选择支持的银行类型：jio, indus','Bank Type Not Supported','Unsupported bank type, supported banks: jio, indus','Please select a supported bank type',NULL,NULL,NULL,NOW(),NOW());

-- IndusBank功能限制错误
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('10213','system','warning','IndusBank does not support second OTP verification','功能不支持','IndusBank不支持二次OTP验证','请使用其他银行或跳过二次验证','Feature Not Supported','IndusBank does not support second OTP verification','Please use another bank or skip second verification',NULL,NULL,NULL,NOW(),NOW());

-- 系统内部错误 (已存在10901，无需重复插入)

-- ===========================================
-- IndusBank 参数验证错误 (200xx)
-- ===========================================

-- 参数验证错误
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('20001','indus','warning','Missing required parameters','参数错误','缺少必需的参数','请检查并提供所有必需的参数','Parameter Error','Missing required parameters','Please provide all required parameters',NULL,NULL,NULL,NOW(),NOW());

-- 手机号格式错误
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('20002','indus','warning','Invalid phone number format','手机号格式错误','手机号格式不正确，应以91开头共12位数字','请输入正确的印度手机号格式','Invalid Phone Format','Phone number should start with 91 and be 12 digits long','Please enter a valid Indian phone number',NULL,NULL,NULL,NOW(),NOW());

-- 银行类型/支付记录未找到
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('20003','indus','error','Bank type not found or payment record not found','记录未找到','银行类型或支付记录未找到','请检查银行类型或支付记录是否存在','Record Not Found','Bank type or payment record not found','Please check if the bank type or payment record exists',NULL,NULL,NULL,NOW(),NOW());

-- 手机号不匹配
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('20005','indus','warning','Phone number mismatch','手机号不匹配','支付记录中的手机号与输入的手机号不匹配','请检查并输入正确的手机号','Phone Number Mismatch','Phone number mismatch for the payment record','Please check and enter the correct phone number',NULL,NULL,NULL,NOW(),NOW());

-- 不支持的步骤
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('20105','indus','warning','Unsupported step','步骤不支持','当前步骤不受支持','请按照正确的流程进行操作','Unsupported Step','Current step is not supported','Please follow the correct process',NULL,NULL,NULL,NOW(),NOW());

-- 预登录处理异常
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('20106','indus','error','Pre-login processing exception','预登录失败','预登录处理过程中发生异常','请稍后重试或联系客服','Pre-login Failed','Pre-login Failed','Please try again later or contact support',NULL,NULL,NULL,NOW(),NOW());

-- ===========================================
-- IndusBank 登录流程错误 (201xx)
-- ===========================================

-- 账户登录状态检查
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('20101','indus','warning','Account is in login process','账户登录中','账户正在登录过程中，请稍后再试','请等待当前登录完成后再试','Account In Process','Account is in login process, please try again later','Please wait for current login to complete',NULL,NULL,NULL,NOW(),NOW());

-- 重复登录检查
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('20102','indus','warning','Account already logged in or invalid status transition','登录状态错误','账户已登录或状态转换无效','请检查当前登录状态或重新开始登录流程','Login Status Error','Account already logged in or invalid status transition','Please check current login status or restart login process',NULL,NULL,NULL,NOW(),NOW());

-- 登录流程已开始
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('20103','indus','warning','Account already started login process','登录流程已开始','账户已开始登录流程，拒绝重复登录','请等待当前登录流程完成','Login Already Started','Account already started login process, duplicate login denied','Please wait for current login process to complete',NULL,NULL,NULL,NOW(),NOW());

-- 登录流程进行中
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('20104','indus','warning','Login process in progress','登录进行中','登录流程正在进行中，拒绝重复登录','请等待当前登录流程完成','Login In Progress','Login process in progress, duplicate login denied','Please wait for current login process to complete',NULL,NULL,NULL,NOW(),NOW());

-- ===========================================
-- IndusBank 会话管理错误 (202xx)  
-- ===========================================

-- 会话不存在或已过期
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('20201','indus','warning','Session does not exist or has expired','会话已过期','登录会话不存在或已过期','请重新开始登录流程','Session Expired','Login session does not exist or has expired','Please restart the login process',NULL,NULL,NULL,NOW(),NOW());

-- 状态转换失败
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('20202','indus','error','Status transition failed','状态转换失败','登录状态转换失败','请重新开始登录流程','Status Transition Failed','Login status transition failed','Please restart the login process',NULL,NULL,NULL,NOW(),NOW());

-- SMS验证会话过期
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('20208','indus','warning','SMS verification session expired','短信验证会话过期','短信验证会话不存在或已过期','请重新发送短信验证','SMS Session Expired','SMS verification session does not exist or has expired','Please restart SMS verification',NULL,NULL,NULL,NOW(),NOW());

-- ===========================================
-- IndusBank 银行API交互错误 (203xx)
-- ===========================================

-- 握手失败
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('20301','indus','error','Handshake failed','握手失败','与银行服务器握手失败','请检查网络连接并重试','Handshake Failed','Handshake with bank server failed','Please check network connection and try again',NULL,NULL,NULL,NOW(),NOW());

-- 认证失败
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('20302','indus','error','Authentication failed','认证失败','银行认证失败','请检查账户信息并重试','Authentication Failed','Bank authentication failed','Please check account information and try again',NULL,NULL,NULL,NOW(),NOW());

-- 设备检查失败
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('20303','indus','error','Device check failed','设备检查失败','设备验证检查失败','请确保设备信息正确并重试','Device Check Failed','Device verification check failed','Please ensure device information is correct and try again',NULL,NULL,NULL,NOW(),NOW());

-- SMS配置失败
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('20304','indus','error','Generate SMS configuration failed','短信配置失败','生成短信配置失败','请重新开始登录流程','SMS Config Failed','Generate SMS configuration failed','Please restart the login process',NULL,NULL,NULL,NOW(),NOW());

-- 短信验证失败
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('20305','indus','error','SMS verification failed','短信验证失败','短信验证过程失败','请重新发送短信验证码','SMS Verification Failed','SMS verification process failed','Please resend SMS verification code',NULL,NULL,NULL,NOW(),NOW());

-- OTP发送失败
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('20306','indus','error','OTP send failed','OTP发送失败','OTP验证码发送失败','请重新发送OTP验证码','OTP Send Failed','OTP verification code send failed','Please resend OTP verification code',NULL,NULL,NULL,NOW(),NOW());

-- OTP验证失败
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('20307','indus','error','OTP verification failed','OTP验证失败','OTP验证码验证失败','请检查验证码是否正确','OTP Verification Failed','OTP verification code validation failed','Please check if the verification code is correct',NULL,NULL,NULL,NOW(),NOW());

-- PIN验证失败
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('20308','indus','error','PIN verification failed','PIN验证失败','PIN密码验证失败','请检查PIN密码是否正确','PIN Verification Failed','PIN password verification failed','Please check if the PIN password is correct',NULL,NULL,NULL,NOW(),NOW());

-- 综合验证异常
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('20309','indus','error','Verification process exception','验证过程异常','SMS/OTP/PIN验证或UPI设置过程中发生异常','请重新开始验证流程','Verification Exception','Exception occurred during SMS/OTP/PIN verification or UPI setup','Please restart the verification process',NULL,NULL,NULL,NOW(),NOW());

-- ===========================================
-- IndusBank 业务逻辑错误 (204xx, 205xx, 206xx)
-- ===========================================

-- OTP业务错误
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('20401','indus','error','Send OTP failed','OTP发送失败','发送OTP验证码失败','请稍后重试发送OTP','Send OTP Failed','Failed to send OTP verification code','Please try sending OTP again later',NULL,NULL,NULL,NOW(),NOW());

-- UPI选择无效
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('20501','indus','warning','Selected UPI is invalid','UPI选择无效','选择的UPI无效或不可用','请选择其他有效的UPI','Invalid UPI Selection','Selected UPI is invalid or unavailable','Please select another valid UPI',NULL,NULL,NULL,NOW(),NOW());

-- 数据库写入失败
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('20601','indus','error','Database write failed','数据库写入失败','数据库操作失败，请重试','请稍后重试，如问题持续请联系客服','Database Error','Database write operation failed','Please try again later or contact support if the problem persists',NULL,NULL,NULL,NOW(),NOW());

-- 2025-7-05 小数点上浮下浮处理
INSERT INTO `channel`
(`code`, name, `type`, url, rate, rates, amount_min, amount_max, amount_fixed, fixed, status, decimal_callback_enabled, time_update, time_create, decimal_min, decimal_max)
VALUES(1005, '唤醒', 1, '1', 0.0001, '0.002,0.001', 1.00, 50000.00, NULL, 0, 1, 0, '2024-11-30 22:43:23', '2023-12-10 19:39:54', 0.01, 0.99);

-- 2025-7-3 对接qqpay新增代收代付账户
INSERT INTO otherpay (merchant_id, `key`, name, pay_url, channel_code, notify_ip, query_url)
VALUES ('146', 'jbhqpyygqlwowlensimkkdaanfxmzcht','qqpay', 'https://api.qq-pay.vip/qpay/payin', 1004, '15.207.191.87,43.205.189.141', 'https://api.qq-pay.vip/qpay/order');
INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `notify_ip`, `query_url`, `status`)
VALUES ('146', 'jbhqpyygqlwowlensimkkdaanfxmzcht', 'https://api.qq-pay.vip/qpay/payout', 'qqpay', 'qqpay支付', NULL, 0, 0, '15.207.191.87,43.205.189.141', 'https://api.qq-pay.vip/qpay/order', 1);

-- refs-296 start ----------------------------------------
-- hins
-- 2025-07-01

-- 查出 “系统设置” 的根节点ID
SELECT id INTO @ssid FROM permissions WHERE name = '系统设置' AND type = 0 AND status = 1 LIMIT 1;

-- 插入 “代收配置”，自动生成 ID，并保存为变量 @pid1
INSERT INTO permissions (pid, name, path, type, status, level, admin_id)
VALUES (@ssid, '代收配置', '', 0, 1, 2, 1);
SET @pid1 = LAST_INSERT_ID();

-- 插入 “代付配置”，自动生成 ID，并保存为变量 @pid2
INSERT INTO permissions (pid, name, path, type, status, level, admin_id)
VALUES (@ssid, '代付配置', '', 0, 1, 2, 1);
SET @pid2 = LAST_INSERT_ID();

-- 插入 “代收配置”下的权限（使用 @pid1）
INSERT INTO permissions (pid, name, path, type, status, level, admin_id)
VALUES 
(@pid1, '查看', '/setting/getdssettings', 1, 1, 2, 1),
(@pid1, '新增', '/setting/adddssettings', 1, 1, 2, 1),
(@pid1, '删除', '/setting/deldssettings', 1, 1, 2, 1),
(@pid1, '编辑', '/setting/edtdssettings', 1, 1, 2, 1);

-- 插入 “代付配置”下的权限（使用 @pid2）
INSERT INTO permissions (pid, name, path, type, status, level, admin_id)
VALUES 
(@pid2, '查看', '/setting/getdfsettings', 1, 1, 2, 1),
(@pid2, '新增', '/setting/adddfsettings', 1, 1, 2, 1),
(@pid2, '删除', '/setting/deldfsettings', 1, 1, 2, 1),
(@pid2, '编辑', '/setting/edtdfsettings', 1, 1, 2, 1);

-- refs-296 end ----------------------------------------

-- 2025-06-21 代付订单拆单处理
-- 描述：父订单ID，0表示是主订单，默认值为0
ALTER TABLE `orders_df`
ADD COLUMN `parent_id` varchar(64) DEFAULT '' COMMENT '父订单ID（0表示是主订单）';
-- 描述：是否拆单处理，1为拆单，0为未拆单，默认值为0
ALTER TABLE `orders_df`
ADD COLUMN `is_split` TINYINT DEFAULT 0 COMMENT '是否拆单处理（1为拆单；0：未拆单）';
ALTER TABLE `orders_df` 
ADD COLUMN `is_del` tinyint(1) NULL DEFAULT 0 COMMENT '0/1  1：删除';

INSERT INTO `permissions` (`pid`, `name`, `path`, `type`, `status`, `level`, `admin_id`) VALUES (10, '代付子单查看', '/partner/getOrderDfSplit', 1, 1, 2, 1);
INSERT INTO `permissions` (`pid`, `name`, `path`, `type`, `status`, `level`, `admin_id`) VALUES (10, '代付拆单', '/partner/confirmSplitOrder', 1, 1, 2, 1);

--2025-7-1 修改third_pay_df notify_ip字段长度
ALTER TABLE `third_pay_df` MODIFY COLUMN `notify_ip` varchar(256);

-- 2025-6-25 接入第三方代付 VibraPay
INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `notify_ip`, `query_url`, `status`, `mer_key2`, `mer_key3`, `mer_key4`)
VALUES ('INR_test', '9f485c70bb0229895f08842a553c487c', 'https://api.vibra-pay.com/v3/withdraw', 'VibraPay', 'VibraPay支付', NULL, 0, 0, '18.180.52.46,18.178.159.1,54.248.121.247', 'https://api.vibra-pay.com/v3/check_withdraw', 1, '93b75a863af6ece0', '', NULL);
--2025-6-25 新增Vibrapay代收
INSERT INTO otherpay (merchant_id, `key`,`key2`, name, pay_url, channel_code, notify_ip, query_url)
VALUES ('INR_test', '9f485c70bb0229895f08842a553c487c', '93b75a863af6ece0','Vibrapay', 'https://api.vibra-pay.com/v3/deposit', 1004, '18.180.52.46,18.178.159.1,54.248.121.247', 'https://api.vibra-pay.com/v3/check');

-- 2025-6-23 TataPay代付开发 收付一体 t100037
INSERT INTO third_pay_df (mer_id, mer_key, pay_url, pay_name, pay_name_zh, channel_code, is_self, is_xiaoshu, notify_ip, query_url, status, mer_key2, mer_key3, mer_key4)
VALUES ('t100037', 'QFr0a6UoL726s62hn7Y2', 'https://api.tatapay.xyz/api/payOut', 'TataPay', 'TataPay支付t100037', NULL, 0, 0, '13.200.39.182', 'https://api.tatapay.xyz/api/payOut/query', 1, '', '', NULL);

-- 2025-06-22 新增TataPay代收
INSERT INTO otherpay (merchant_id, `key`, name, pay_url, channel_code, notify_ip, query_url)
VALUES ('t100037', 'QFr0a6UoL726s62hn7Y2', 'TataPay_t100037', 'https://api.tatapay.xyz/api/payIn', 1004, '13.200.39.182', 'https://api.tatapay.xyz/api/payIn/query');
ALTER TABLE `merchant` ADD COLUMN `decimal_amt_flag` TINYINT(1) DEFAULT 0 COMMENT '商户小数点回调开关 0-关闭 1-开启' AFTER `status_df`;

-- 2025-06-18 商户+通道双重小数点回调控制
ALTER TABLE `merchant` ADD COLUMN `decimal_amt_flag` TINYINT(1) DEFAULT 0 COMMENT '商户小数点回调开关 0-关闭 1-开启' AFTER `status_df`;
-- 添加Notify回调类型字段
ALTER TABLE `merchant` ADD COLUMN `notify_callback_type` TINYINT(1) DEFAULT 0 COMMENT 'Notify回调类型 0-整数回调 1-小数点回调' AFTER `decimal_amt_flag`;

-- 更新现有数据，默认关闭小数点回调
UPDATE `merchant` SET `decimal_amt_flag` = 0 WHERE `decimal_amt_flag` IS NULL;

-- 更新现有数据，默认整数回调
UPDATE `merchant` SET `notify_callback_type` = 0 WHERE `notify_callback_type` IS NULL;
-- 2025-06-18 新增码商登录历史记录表
CREATE TABLE partner_login_log (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT 'ID',
    partner_id INT NOT NULL COMMENT '码商ID',
    ip VARCHAR(45) NOT NULL COMMENT '登录IP',
    ref VARCHAR(255) COMMENT '访问站点',
    loc VARCHAR(255) NOT NULL COMMENT 'IP位置',
    created_at timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '登录时间'
) ENGINE=InnoDB COMMENT = '码商登录历史记录';

-- 2025-06-04 为channel表添加小数点回调标识字段
ALTER TABLE `channel` ADD COLUMN decimal_callback_enabled TINYINT(1) DEFAULT 0 COMMENT '是否为小数点回调通道 0-否 1-是' AFTER status;
ALTER TABLE `channel` ADD COLUMN decimal_min DECIMAL(3,2) DEFAULT 0.01 COMMENT '小数点范围最小值';
ALTER TABLE `channel` ADD COLUMN decimal_max DECIMAL(3,2) DEFAULT 0.99 COMMENT '小数点范围最大值';
ALTER TABLE `orders_ds` ADD COLUMN `original_amount` decimal(14,4) NULL COMMENT '小数点回调订单的原始金额';
-- 错误消息表
CREATE TABLE IF NOT EXISTS `error_messages` (
  `error_code` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL,
  `module` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `severity` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `technical_message` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `zh_title` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `zh_message` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `zh_action` text COLLATE utf8mb4_unicode_ci,
  `en_title` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `en_message` text COLLATE utf8mb4_unicode_ci,
  `en_action` text COLLATE utf8mb4_unicode_ci,
  `hi_title` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `hi_message` text COLLATE utf8mb4_unicode_ci,
  `hi_action` text COLLATE utf8mb4_unicode_ci,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`error_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT = '错误信息表';

-- 错误消息数据
INSERT INTO `error_messages` (`error_code`, `module`, `severity`, `technical_message`, `zh_title`, `zh_message`, `zh_action`, `en_title`, `en_message`, `en_action`, `hi_title`, `hi_message`, `hi_action`, `created_at`, `updated_at`) VALUES
('10001','network','warning','网络连接失败','网络连接问题','无法连接到服务器','请检查您的网络连接并重试','Network Error','Network connection failed.',NULL,NULL,NULL,NULL,'2025-05-08 14:29:15','2025-05-08 14:29:15'),
('10002','network','warning','WebSocket连接断开','连接已断开','与服务器的连接已断开','请刷新页面重新连接','Connection Lost','Connection lost. Please refresh the page',NULL,NULL,NULL,NULL,'2025-05-08 14:29:22','2025-05-08 14:29:22'),
('10101','system','warning','会话过期/无效Token','登录已过期','您的登录状态已过期','请重新登录系统','Login Expired','Login expired. Please log in again.',NULL,NULL,NULL,NULL,'2025-05-08 14:29:27','2025-05-08 14:29:27'),
('10102','system','info','发送验证码成功','验证码已发送','验证码已成功发送','请查看短信并输入收到的验证码','Code Sent','Verification sent successfully',NULL,NULL,NULL,NULL,'2025-05-08 14:29:33','2025-05-08 14:29:33'),
('10104','system','error','系统内部错误','系统繁忙','系统暂时无法处理您的请求','请稍后再试，或联系客服报告此问题','System Busy','System busy. Please try again later.',NULL,NULL,NULL,NULL,'2025-05-08 14:29:40','2025-05-08 14:29:40'),
('10201','general','error','Bank not found','银行未找到','找不到指定的银行信息',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'2025-05-08 13:58:11','2025-05-08 13:58:11'),
('10202','payment','error','Payment Password Incorrect','支付密码错误','您输入的支付密码不正确',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'2025-05-08 13:58:11','2025-05-08 13:58:11'),
('10203','login','warning','手机号已存在','手机号已注册','该手机号已关联其他账号','请使用其他手机号注册，或直接登录已有账号','Phone Number Registered','Phone number already registered.',NULL,NULL,NULL,NULL,'2025-05-08 14:28:13','2025-05-08 14:28:13'),
('10204','login','warning','验证码错误','验证码不正确','您输入的验证码有误','请重新输入正确的验证码，或点击\"重新获取\"获取新的验证码','Incorrect Code','Incorrect verification code. Please try again.',NULL,NULL,NULL,NULL,'2025-05-08 14:28:19','2025-05-08 14:28:19'),
('10205','login','info','注册成功','注册成功','账号注册成功','请使用新账号登录系统','Registration Successful','Registration successful.',NULL,NULL,NULL,NULL,'2025-05-08 14:28:24','2025-05-08 14:28:24'),
('10206','login','error','注册失败','注册失败','账号注册失败，系统暂时无法完成注册','请稍后再试，或联系客服获取帮助','Registration Failed','Registration failed. Please try again later.',NULL,NULL,NULL,NULL,'2025-05-08 14:28:29','2025-05-08 14:28:29'),
('10207','login','warning','账号不存在','账号未找到','您输入的账号不存在','请检查输入的账号是否正确，或点击\"注册账号\"创建新账号','Account Not Found','Account not found. Please check or register a new account.',NULL,NULL,NULL,NULL,'2025-05-08 14:28:35','2025-05-08 14:28:35'),
('10208','login','warning','密码长度不足','密码不符合要求','密码长度需要至少6位','请输入至少6位的密码','Invalid Password','Password must be at least 8-20 characters.',NULL,NULL,NULL,NULL,'2025-05-08 14:28:40','2025-05-08 14:28:40'),
('10209','login','warning','手机号格式错误','手机号格式错误','您输入的手机号格式不正确','请输入正确的10位手机号码','Invalid Phone Number','Please enter a 10-digit phone number',NULL,NULL,NULL,NULL,'2025-05-08 14:28:46','2025-05-08 14:28:46'),
('10301','general','error','Payment not found or access denied','支付未找到','找不到指定的支付信息或无权访问',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'2025-05-08 13:58:11','2025-05-08 13:58:11'),
('10302','payment','warning','卡片信息无效','卡片信息错误','提供的卡片信息无效','请检查卡号、持卡人姓名等信息是否正确','Invalid Card','Invalid card information.',NULL,NULL,NULL,NULL,'2025-05-08 14:28:52','2025-05-08 14:28:52'),
('10303','payment','warning','网络连接错误','网络连接不稳定','系统无法连接到支付服务','请检查您的网络连接并重试，或切换到其他网络','Network Error','Network error',NULL,NULL,NULL,NULL,'2025-05-08 14:28:58','2025-05-08 14:28:58'),
('10304','payment','error','银行验证失败','银行验证失败','银行无法验证您的卡片信息','请确认卡片状态正常且有足够余额，或联系发卡银行','Bank Verification Failed','Bank verification failed. Please check your card status or contact your bank.',NULL,NULL,NULL,NULL,'2025-05-08 14:29:04','2025-05-08 14:29:04'),
('10305','payment','warning','激活请求超时','请求超时','激活请求处理时间过长','系统可能正忙，请稍后再试或检查网络连接','Request Timeout','Request timed out.',NULL,NULL,NULL,NULL,'2025-05-08 14:29:09','2025-05-08 14:29:09'),
('10401','payment','info','UPI already exists and belongs to current user','UPI已存在','该UPI已存在且属于您的账号','请在UPI列表中激活该UPI','UPI Exists','This UPI already exists in your account. Please activate it from your UPI list.',NULL,NULL,NULL,NULL,'2025-05-08 14:30:00','2025-05-08 14:30:00'),
('10402','payment','warning','UPI already occupied','UPI已被占用','该UPI已被其他账号使用','请使用其他UPI进行绑定','UPI Occupied','This UPI is already in use by another account. Please use a different UPI.',NULL,NULL,NULL,NULL,'2025-05-08 14:30:05','2025-05-08 14:30:05'),
('10403','payment','error','Failed to send OTP','OTP发送失败','系统无法发送验证码','请检查您的手机号是否正确，或稍后再试','OTP Failure','Failed to send OTP. Please check your phone number or try again later.',NULL,NULL,NULL,NULL,'2025-05-08 14:30:10','2025-05-08 14:30:10'),
('10601','business','info','订单已存在','订单重复','已存在相同的订单','请勿重复提交相同订单','Order Exists','Order already exists. Please do not submit again.',NULL,NULL,NULL,NULL,'2025-05-08 14:29:46','2025-05-08 14:29:46'),
('10602','business','warning','订单不存在','订单未找到','未找到相关订单信息','请检查订单号是否正确','Order Not Found','Order not found.',NULL,NULL,NULL,NULL,'2025-05-08 14:29:51','2025-05-08 14:29:51'),
('10605','business','warning','操作权限不足','权限不足','您没有执行此操作的权限','请联系管理员获取权限，或使用其他账号','Permission Denied','Permission denied.',NULL,NULL,NULL,NULL,'2025-05-08 14:29:57','2025-05-08 14:29:57'),
('10901','system','error','System Error','系统错误','发生系统错误，请联系客服',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'2025-05-08 13:58:11','2025-05-08 13:58:11');
alter table partner alter column balance set default 0;
alter table partner alter column balance_frozen set default 0;
alter table partner alter column balance_df set default 0;
alter table merchant alter column balance set default 0;
alter table merchant alter column balance_frozen set default 0;
alter table merchant alter column balance_df set default 0;
alter table merchant alter column rate_df set default 0;
alter table merchant alter column fee_df set default 0;
alter table payment alter column amount set default 0;
alter table partner_withdraw alter column amount_order set default 0;
alter table merchant_withdraw alter column amount_order set default 0;

ALTER TABLE `ospay`.`orders_ds` MODIFY COLUMN `earn_system` decimal(10, 4) DEFAULT 0 COMMENT '平台盈利';
ALTER TABLE `ospay`.`orders_ds` MODIFY COLUMN `merchant_rate` decimal(10,4) DEFAULT 0 COMMENT '商户费率';
ALTER TABLE `ospay`.`orders_ds` MODIFY COLUMN `earn_merchant` decimal(10,4) DEFAULT 0 COMMENT '商户总盈利';
ALTER TABLE `ospay`.`orders_ds` MODIFY COLUMN `earn_partner_self` decimal(14,4) DEFAULT 0 COMMENT '码商盈利';
ALTER TABLE `ospay`.`orders_ds` MODIFY COLUMN `earn_partner` decimal(10,4) DEFAULT 0 COMMENT '码商总盈利';


-- 2023-12-31 -- 添加第三方  Razorpay-upi原生
ALTER TABLE `otherpay` ADD COLUMN `key2` varchar(255) CHARACTER SET utf8 COLLATE utf8_unicode_ci DEFAULT NULL COMMENT '可以放公钥' AFTER `key`,
ADD COLUMN `key3` varchar(255) CHARACTER SET utf8 COLLATE utf8_unicode_ci DEFAULT NULL COMMENT '可以放私钥' AFTER `key2`;
ALTER TABLE `otherpay` CHANGE COLUMN `query_ip` `query_url` varchar(255) CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT NULL COMMENT '查询网关' AFTER `notify_ip`;
ALTER TABLE `ospay`.`otherpay` MODIFY COLUMN `merchant_id` varchar(255) DEFAULT NULL COMMENT '商户ID' AFTER `id`;
INSERT INTO otherpay ( `merchant_id`, `key`, `key2`, `key3`, `pay_url`, `name`, `channel_code`, `query_url`) VALUES ('N97Xl8VgbPt6SS', 'rzp_live_ypcALV6XkPZXo2', 'VbX8DZhp4j85yfZ6U7RtDpBZ', '' , 'https://api.razorpay.com/v1/payment_links', 'Razorpay-upi-origin', '1002', 'https://api.razorpay.com/v1/payment_links/');

-- 2024-01-03 -- phonepe
CREATE TABLE phonepe (
  id int NOT NULL AUTO_INCREMENT COMMENT 'ID',
  pw varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL DEFAULT '123456' COMMENT '密码',
  payment_id int DEFAULT NULL COMMENT '码ID',
  status int NOT NULL DEFAULT '0' COMMENT '0 未连接 1已连接',
  occupied int NOT NULL DEFAULT '0' COMMENT '使用中',
  time_create datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (id)
) ENGINE=InnoDB AUTO_INCREMENT=1003 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- 2024-01-03 -- 充值
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
  `ifsc` varchar(64) COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT 'ifsc',
  `account` varchar(64) COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT 'account',
  `name` varchar(64) COLLATE utf8mb3_unicode_ci DEFAULT NULL COMMENT 'name',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=14 DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_unicode_ci COMMENT='码商提现';

-- 2024-01-05 -- 码商充值 系统卡表
ALTER TABLE `sys_payment` MODIFY COLUMN `type` varchar(64) CHARACTER SET utf8 COLLATE utf8_unicode_ci NOT NULL DEFAULT 1 COMMENT '类型 默认1 bank' AFTER `name`;
ALTER TABLE `sys_payment` ADD COLUMN `bank` varchar(64) NULL COMMENT '银行名称' AFTER `ifsc`;
ALTER TABLE `sys_payment` ADD UNIQUE INDEX `account`(`account`) USING BTREE;

ALTER TABLE `partner_recharge` ADD COLUMN `bank` varchar(64) COLLATE utf8_unicode_ci DEFAULT NULL COMMENT '银行';
ALTER TABLE `partner_recharge` ADD UNIQUE INDEX `code`(`code`) USING HASH;
ALTER TABLE `balance_record` MODIFY COLUMN `record_type` int(11) NOT NULL DEFAULT 0 COMMENT '流水类型 0代收 1代付 2提现 3佣金 4冻结 5押金 6人工 7充值' AFTER `change_after`;

INSERT INTO `permissions` (`pid`, `name`, `path`, `type`, `status`) VALUES (8, '码商充值订单', '', 0, 1)

-- 代付下单抢单
ALTER TABLE `partner` ADD COLUMN `type` int DEFAULT 1 COMMENT '码商类型 0内部 1外部';
ALTER TABLE `orders_df` ADD COLUMN `sys_remark` varchar(255) COLLATE utf8_unicode_ci DEFAULT NULL COMMENT '系统备注';
ALTER TABLE `orders_df` ADD COLUMN `certified` int(11) NOT NULL DEFAULT '0' COMMENT '0未认证 1已认证';

-- 添加邀请码 --
ALTER TABLE `partner` ADD COLUMN `invitation_code` varchar(8) COLLATE utf8_unicode_ci COMMENT '邀请码';
ALTER TABLE `ospay`.`partner` ADD UNIQUE INDEX `invitation_code`(`invitation_code`) USING BTREE;

ALTER TABLE `orders_ds` ADD INDEX `id_time_create`(`id`, `time_create`);
ALTER TABLE `orders_ds` ADD INDEX `time_create`(`time_create`);

-- 2024-01-11 -- 码商转账
CREATE TABLE `transfer` (
  `id` int(11) NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `code` varchar(64) COLLATE utf8_unicode_ci NOT NULL COMMENT '订单号',
  `partner_id` int(11) NOT NULL COMMENT 'ID',
  `to_partner_id` int(11) NOT NULL COMMENT '要转入的ID',
  `amount` decimal(12,2) NOT NULL COMMENT '订单金额',
  `admin_id` int(11) DEFAULT NULL COMMENT '管理员ID',
  `status` int(11) NOT NULL DEFAULT '1' COMMENT '订单状态 0待处理 1处理中 2已完成 -1已取消',
  `time_success` datetime DEFAULT NULL COMMENT '成功时间',
  `time_updated` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `time_create` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '下单时间',
  `type` int(11) NOT NULL DEFAULT '1' COMMENT '类型 1码商互转',
  `remark` varchar(255) COLLATE utf8_unicode_ci DEFAULT NULL COMMENT '备注',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `code` (`code`) USING HASH
) ENGINE=InnoDB AUTO_INCREMENT=37 DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci COMMENT='转账表';

ALTER TABLE `permissions` MODIFY COLUMN `id` int(11) NOT NULL AUTO_INCREMENT COMMENT 'ID' FIRST,AUTO_INCREMENT = 40;
INSERT INTO `permissions` (`pid`, `name`, `path`, `type`, `status`) VALUES (8, '码商转账订单', '', 0, 1);
ALTER TABLE `balance_record` MODIFY COLUMN `record_type` int(11) NOT NULL DEFAULT 0 COMMENT '流水类型 0代收 1代付 2提现 3佣金 4冻结 5押金 6人工 7充值 8转账' AFTER `change_after`

-- 添加邀请码 --
ALTER TABLE `partner` ADD COLUMN `ew_code` varchar(64) COLLATE utf8_unicode_ci COMMENT '额外扣款流水';

ALTER TABLE `merchant_withdraw` ADD COLUMN `admin_id` int(11) NULL DEFAULT NULL COMMENT '管理员' AFTER `time_create`;
ALTER TABLE `merchant_withdraw` MODIFY COLUMN `status` int(11) NOT NULL DEFAULT 0 COMMENT '状态 0下单 1处理 2完成 -1驳回' AFTER `amount`;

-- 增加码商转账确认驳回权限-
INSERT INTO `ospay`.`permissions` (`pid`, `name`, `path`) VALUES (8, '码商转账确认驳回', '/partner/handletransfer');
-- 增加修改码商权限-
INSERT INTO `ospay`.`permissions` (`pid`, `name`, `path`) VALUES (19, '修改码商', '/partner/updatepartner');
INSERT INTO `ospay`.`permissions` (`pid`, `name`, `path`) VALUES (19, '删除二维码', '/partner/deletepayment');

ALTER TABLE `ospay`.`orders_ds` ADD INDEX `merchant_id_status_time_create`(`status`, `time_create`, `merchant_id`);

-- 商户代付白名单-
ALTER TABLE `merchant` ADD COLUMN `ip_df` varchar(255) NULL COMMENT '代付白名单' AFTER `ip`;
ALTER TABLE `balance_record` ADD INDEX `time_create`(`time_create`);
ALTER TABLE `balance_record` ADD INDEX `code`(`code`);

-- 优化商户排名查询
ALTER TABLE `ospay`.`orders_ds` ADD INDEX `merchant_id_time_create`(`merchant_id`, `time_create`);
-- 代收代付查询
ALTER TABLE `orders_ds` ADD INDEX `time_success`(`time_success`);
ALTER TABLE `orders_df` ADD INDEX `payment_id_status`(`payment_id`, `status`);
ALTER TABLE `orders_ds` ADD INDEX `utr_time_create`(`utr`, `time_create`);
INSERT INTO `bank_type`(`name`, `url`) VALUES ('BOB BANK', NULL);

ALTER TABLE `bank_record` ADD COLUMN `ew_code` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '额外流水号' AFTER `time_create`;

-- 添加EQUITAS銀行
INSERT INTO `bank_type`(`name`, `url`) VALUES ('EQUITAS', "https://inet.equitasbank.com/EquitasCorp/#");
ALTER TABLE `orders_ds` ADD INDEX `amount_auth_code_status_time_create`(`amount`, `status`, `time_create`, `auth_code`);

ALTER TABLE `bank_record` MODIFY COLUMN `content` varchar(1280) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '采集内容' AFTER `amount`;
ALTER TABLE `orders_df` ADD INDEX `time_accept`(`time_accept`);

ALTER TABLE `bank_record` add  `invalid` int(11) DEFAULT '0' COMMENT '失效';
ALTER TABLE `bank_type` ADD COLUMN `type` int(10) NULL DEFAULT 0 COMMENT '显示类型 0内部码商显示 1外部显示' AFTER `url`;

# bank_record表添加partner_id
ALTER TABLE `ospay`.`bank_record`  ADD COLUMN `partner_id` int NOT NULL COMMENT '码商id';

ALTER TABLE `ospay`.`bank_record`  ADD INDEX `ind_partner_id_time_create`(`partner_id`, `time_create`) USING BTREE;

# vip表添加押金比例
ALTER TABLE `ospay`.`vip` ADD COLUMN `deposit_ratio` tinyint(1) NOT NULL DEFAULT 20 COMMENT '押金比例';

ALTER TABLE `orders_ds` MODIFY COLUMN `remark` varchar(300) CHARACTER SET utf8 COLLATE utf8_general_ci NULL DEFAULT NULL COMMENT '备注' AFTER `player_ip`;
ALTER TABLE `ospay`.`payment` MODIFY COLUMN `upi` varchar(64) CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT NULL COMMENT 'UPI' AFTER `account_type`;
ALTER TABLE `ospay`.`payment_d` MODIFY COLUMN `upi` varchar(64) CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT NULL COMMENT 'UPI' AFTER `account_type`;

ALTER TABLE `ospay`.`bank_type` ADD COLUMN `status` tinyint(1) NULL DEFAULT 1 COMMENT '0禁用1启用' ;
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (40, 19, '银行管理', '', 0, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (41, 22, '收款资料批量禁用', '/partner/batchDisablePayment', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (42, 40, '银行管理查询', '/partner/getBankType', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (43, 40, '银行管理修改状态', '/partner/updateBankTypeStatus', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (44, 40, '银行管理编辑', '/partner/updateBankType', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (45, 40, '银行管理添加', '/partner/addBankType', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (46, 40, '银行管理删除', '/partner/deleteBankType', 1, 1);

ALTER TABLE `balance_record` MODIFY COLUMN `record_type` int(11) NOT NULL DEFAULT 0 COMMENT '流水类型 0代收 1代付 2提现 3佣金 4冻结 5押金 6人工 7充值 8转账 9驳回';
ALTER TABLE `balance_record` MODIFY COLUMN `record_type` int(11) NOT NULL DEFAULT 0 COMMENT '流水类型 0代收 1代付 2提现 3佣金 4冻结 5押金 6人工 7充值 8转账 9驳回 10代付优惠';

# 余额统计添加外部内部统计字段
ALTER TABLE `ospay`.`balance_count_record`
ADD COLUMN `balance_p_frozen_outside` decimal(14, 4) NOT NULL COMMENT '外部码商冻结余额' ,
ADD COLUMN `balance_p_outside` decimal(14, 4) NOT NULL COMMENT '外部码商余额',
ADD COLUMN `balance_p_inside` decimal(14, 4) NOT NULL COMMENT '内部码商余额' ,
ADD COLUMN `balance_p_frozen_inside` decimal(14, 4) NOT NULL COMMENT '内部码商冻结余额' ;

# 二维码连续10单锁码，人工解锁
ALTER TABLE `ospay`.`payment` ADD COLUMN `manual_status` tinyint(1) NOT NULL DEFAULT 0 COMMENT '0 未锁定 1 二维码连续10单锁码，人工解锁';
# 0额外流水号为空1额外流水号有值
ALTER TABLE ospay.bank_record ADD COLUMN if_ew tinyint NULL DEFAULT 0 COMMENT 'ew_code为空则为0，不为空则为1' AFTER partner_id;
# 查询码商余额是否足够, 要减去爬取后的账单中该扣未扣的金额添加索引
ALTER TABLE ospay.bank_record ADD INDEX  payment_id_trade_type_if_ew_invalid_callback(payment_id, trade_type,if_ew, invalid, callback);
# 角色添加加密字段
ALTER TABLE `ospay`.`roles` ADD COLUMN `encryption` tinyint(1) NOT NULL DEFAULT 0 COMMENT '0不加密1加密';
# 添加权限
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (47, 22, '查看/导出', '/partner/getpayment', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (51, 22, '限额/reject/pass/禁用/启用/人工锁定/人工解锁/correction', '/partner/updatepayment', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (52, 22, '删除', '/partner/deletepayment', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (53, 22, '重置', '/partner/resettingPayment', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (55, 24, 'add', '/partner/addbank_recoed', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (56, 24, '废除', '/partner/delbank_recoed', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (57, 24, '查看/导出', '/partner/getbank_recoed', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (58, 20, '查看/导出', '/partner/getpartner', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (59, 20, '新增码商', '/partner/addpartner', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (60, 20, '编辑/锁定', '/partner/updatepartner', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (62, 9, '查看/导出', '/order/getorderds', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (63, 9, '补单', '/order/handleorder', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (64, 9, '手动回调', '/order/handlenotifyds', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (65, 9, '第三方补单', '/order/handleOrderFromThird', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (66, 10, '查看/导出', '/order/getorderdf', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (68, 10, '上传凭证', '/files/upload', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (69, 10, '手动回调', '/order/handlenotifydf', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (70, 10, '驳回', '/order/cancelorderdf', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (71, 9, '商户处理中/已完成聚合', '/order/getDSMerchantFinishOrProcessing', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (72, 10, '商户处理中/已完成聚合', '/order/getDFMerchantFinishOrProcessing', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (73, 10, '确认', '/order/handleOrderdfType1', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (74, 10, '上传凭证确认', '/order/handleOrderdfType2', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (75, 10, '改派', '/order/handleOrderdfType3', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (76, 10, '分配账号', '/order/handleOrderdfType4', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (77, 10, '代付拆单回退', '/order/handleOrderdfRevert', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (78, 10, '批量处理', '/order/handleBatchOrderdf', 1, 1);
UPDATE `ospay`.`roles`
SET permissions = CONCAT(permissions, ',65')
WHERE FIND_IN_SET('63', permissions) > 0
  AND FIND_IN_SET('65', permissions) = 0;
UPDATE `ospay`.`roles`
SET permissions = CONCAT_WS(',', permissions, '71')
WHERE FIND_IN_SET('62', permissions) > 0 AND FIND_IN_SET('71', permissions) = 0;
UPDATE `ospay`.`roles`
SET permissions = CONCAT_WS(',', permissions, '72')
WHERE FIND_IN_SET('66', permissions) > 0 AND FIND_IN_SET('72', permissions) = 0;
UPDATE `ospay`.`roles`
SET permissions = CONCAT_WS(',', permissions, '73')
WHERE FIND_IN_SET('81', permissions) > 0 AND FIND_IN_SET('73', permissions) = 0;
UPDATE `ospay`.`roles`
SET permissions = CONCAT_WS(',', permissions, '74')
WHERE FIND_IN_SET('81', permissions) > 0 AND FIND_IN_SET('74', permissions) = 0;
UPDATE `ospay`.`roles`
SET permissions = CONCAT_WS(',', permissions, '75')
WHERE FIND_IN_SET('81', permissions) > 0 AND FIND_IN_SET('75', permissions) = 0;
UPDATE `ospay`.`roles`
SET permissions = CONCAT_WS(',', permissions, '76')
WHERE FIND_IN_SET('81', permissions) > 0 AND FIND_IN_SET('76', permissions) = 0;
UPDATE `ospay`.`roles`
SET permissions = CONCAT_WS(',', permissions, '77')
WHERE FIND_IN_SET('81', permissions) > 0 AND FIND_IN_SET('77', permissions) = 0;
UPDATE `ospay`.`roles`
SET permissions = CONCAT_WS(',', permissions, '78')
WHERE FIND_IN_SET('81', permissions) > 0 AND FIND_IN_SET('78', permissions) = 0;
# 优先收款
ALTER TABLE `ospay`.`payment` ADD COLUMN `priority_collection` tinyint(1) NOT NULL DEFAULT 0 COMMENT '0 普通收款 1 优先收款' ;
ALTER TABLE `ospay`.`sys_info` ADD COLUMN `status_df` tinyint(1) NOT NULL DEFAULT 0 COMMENT '0停止1开启';
# 码商收款最小和最大金额
ALTER TABLE `ospay`.`partner` ADD COLUMN `ds_min` decimal(12,2) NOT NULL DEFAULT 0.00 COMMENT '代收最小限额';
ALTER TABLE `ospay`.`partner` ADD COLUMN `ds_max` decimal(12,2) NOT NULL DEFAULT 0.00 COMMENT '代收最大限额';

# 新增 AIRTEL BANK
INSERT INTO ospay.bank_type (id, name, url, type, status, logo_url) VALUES (21, 'AIRTEL BANK', '', 1, 1, NULL);
## 统计银行的总收款金额 成功率
INSERT INTO ospay.permissions (id, pid, name, path, type, status) VALUES (80, 19, '银行排名', '/partner/getBankRank', 0, 1);
# 添加权限
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (81, 10, '改派/GET/确认', '/order/handleorderdf', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (82, 20, '迁移码商', '/partner/migratePartner', 1, 1);
# 收款资料添加upi列表
ALTER TABLE `ospay`.`payment` ADD COLUMN `upi_list` varchar(500) NULL COMMENT 'upi列表' ;

# 收款资料添加权重
ALTER TABLE `ospay`.`payment` ADD COLUMN `weight` int(11) default 1 COMMENT '权重';
CREATE TABLE `payment_weight` (
  `id` int(11) NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `value` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '成功率百分比，或其他值',
  `weight` int(11) DEFAULT 1 COMMENT '权重值',
  `payment_ids` longtext DEFAULT NULL COMMENT '所属的id集合，按逗号分开',
  `payment_numbers` int(11) DEFAULT 0 COMMENT 'id数量',
  `type` int(11) DEFAULT 0 COMMENT '0为按成功率，1为按是否新码，2为按是否优先收款',
  `time_updated` datetime DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci COMMENT='收款资料权重表';
INSERT INTO `ospay`.`payment_weight` (`id`, `value`, `weight`, `payment_ids`, `payment_numbers`, `type`, `time_updated`) VALUES (1, 0.00, 1, NULL, 0, 0, '2024-05-26 19:05:13');
INSERT INTO `ospay`.`payment_weight` (`id`, `value`, `weight`, `payment_ids`, `payment_numbers`, `type`, `time_updated`) VALUES (2, 5.00, 1, NULL, 0, 0, '2024-05-26 19:00:54');
INSERT INTO `ospay`.`payment_weight` (`id`, `value`, `weight`, `payment_ids`, `payment_numbers`, `type`, `time_updated`) VALUES (3, 10.00, 1, NULL, 0, 0, '2024-05-26 19:00:54');
INSERT INTO `ospay`.`payment_weight` (`id`, `value`, `weight`, `payment_ids`, `payment_numbers`, `type`, `time_updated`) VALUES (4, 15.00, 1, NULL, 0, 0, '2024-05-26 19:00:54');
INSERT INTO `ospay`.`payment_weight` (`id`, `value`, `weight`, `payment_ids`, `payment_numbers`, `type`, `time_updated`) VALUES (5, 20.00, 1, NULL, 0, 0, '2024-05-26 19:00:54');
INSERT INTO `ospay`.`payment_weight` (`id`, `value`, `weight`, `payment_ids`, `payment_numbers`, `type`, `time_updated`) VALUES (6, 25.00, 1, NULL, 0, 0, '2024-05-26 19:00:54');
INSERT INTO `ospay`.`payment_weight` (`id`, `value`, `weight`, `payment_ids`, `payment_numbers`, `type`, `time_updated`) VALUES (7, 30.00, 1, NULL, 0, 0, '2024-05-26 19:00:54');
INSERT INTO `ospay`.`payment_weight` (`id`, `value`, `weight`, `payment_ids`, `payment_numbers`, `type`, `time_updated`) VALUES (8, 35.00, 1, NULL, 0, 0, '2024-05-26 19:00:54');
INSERT INTO `ospay`.`payment_weight` (`id`, `value`, `weight`, `payment_ids`, `payment_numbers`, `type`, `time_updated`) VALUES (9, 40.00, 1, NULL, 0, 0, '2024-05-26 19:00:54');
INSERT INTO `ospay`.`payment_weight` (`id`, `value`, `weight`, `payment_ids`, `payment_numbers`, `type`, `time_updated`) VALUES (10, 45.00, 1, NULL, 0, 0, '2024-05-26 19:00:54');
INSERT INTO `ospay`.`payment_weight` (`id`, `value`, `weight`, `payment_ids`, `payment_numbers`, `type`, `time_updated`) VALUES (11, 50.00, 1, NULL, 0, 0, '2024-05-26 19:00:54');
INSERT INTO `ospay`.`payment_weight` (`id`, `value`, `weight`, `payment_ids`, `payment_numbers`, `type`, `time_updated`) VALUES (12, 55.00, 1, NULL, 0, 0, '2024-05-26 19:00:54');
INSERT INTO `ospay`.`payment_weight` (`id`, `value`, `weight`, `payment_ids`, `payment_numbers`, `type`, `time_updated`) VALUES (13, 60.00, 1, NULL, 0, 0, '2024-05-26 19:00:54');
INSERT INTO `ospay`.`payment_weight` (`id`, `value`, `weight`, `payment_ids`, `payment_numbers`, `type`, `time_updated`) VALUES (14, 65.00, 1, NULL, 0, 0, '2024-05-26 19:00:54');
INSERT INTO `ospay`.`payment_weight` (`id`, `value`, `weight`, `payment_ids`, `payment_numbers`, `type`, `time_updated`) VALUES (15, 70.00, 1, NULL, 0, 0, '2024-05-26 19:00:54');
INSERT INTO `ospay`.`payment_weight` (`id`, `value`, `weight`, `payment_ids`, `payment_numbers`, `type`, `time_updated`) VALUES (16, 75.00, 1, NULL, 0, 0, '2024-05-26 19:00:54');
INSERT INTO `ospay`.`payment_weight` (`id`, `value`, `weight`, `payment_ids`, `payment_numbers`, `type`, `time_updated`) VALUES (17, 80.00, 1, NULL, 0, 0, '2024-05-26 19:05:10');
INSERT INTO `ospay`.`payment_weight` (`id`, `value`, `weight`, `payment_ids`, `payment_numbers`, `type`, `time_updated`) VALUES (18, 85.00, 1, NULL, 0, 0, '2024-05-26 19:05:10');
INSERT INTO `ospay`.`payment_weight` (`id`, `value`, `weight`, `payment_ids`, `payment_numbers`, `type`, `time_updated`) VALUES (19, 90.00, 1, NULL, 0, 0, '2024-05-26 19:05:10');
INSERT INTO `ospay`.`payment_weight` (`id`, `value`, `weight`, `payment_ids`, `payment_numbers`, `type`, `time_updated`) VALUES (20, 95.00, 1, NULL, 0, 0, '2024-05-26 19:00:54');
INSERT INTO `ospay`.`payment_weight` (`id`, `value`, `weight`, `payment_ids`, `payment_numbers`, `type`, `time_updated`) VALUES (21, 0.00, 1, NULL, 0, 1, '2024-05-26 19:05:13');
INSERT INTO `ospay`.`payment_weight` (`id`, `value`, `weight`, `payment_ids`, `payment_numbers`, `type`, `time_updated`) VALUES (22, 0.00, 1, NULL, 0, 2, '2024-05-26 19:05:10');
# 添加权限
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (83, 34, '修改其他设置', '/setting/updateother', 1, 1);
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (84, 34, '修改权重', '/setting/updateweight', 1, 1);
# 系统信息添加代付过期开关
ALTER TABLE `sys_info` ADD COLUMN `expired_status_df` tinyint(1) UNSIGNED NOT NULL DEFAULT 1 COMMENT '代付过期开关0停止1开启';

-- 2024-05-20
CREATE TABLE `usdt_deposit_orders`
(
    `id`              int                                 NOT NULL AUTO_INCREMENT,
    `serial_number`   varchar(64) COLLATE utf8_unicode_ci NOT NULL COMMENT '序列号',
    `status`          int NOT NULL DEFAULT '0' COMMENT '订单状态 0待处理 1处理中(拿到地址) 2已完成(已支付) -1已取消',
    `usdt_amount`     decimal(12, 4) NOT NULL COMMENT 'USDT',
    `exchange_rate`   decimal(8, 4)  NOT NULL COMMENT '汇率',
    `currency_amount` decimal(12, 4) NOT NULL COMMENT '卢比数额',
    `block_chain`     varchar(64)    NOT NULL COMMENT '区块链',
    `bonus_rate`      decimal(6, 4)  NOT NULL COMMENT '红利比例',
    `bonus`           decimal(10, 4) NOT NULL COMMENT '红利',
    `total_amount`    decimal(12, 4) NOT NULL COMMENT '上分总数',
    `created_at`      datetime       DEFAULT CURRENT_TIMESTAMP  COMMENT '订单生成时间',
    `updated_at`      datetime       DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最後更新时间',
    `paid_at`         datetime       DEFAULT NULL COMMENT '支付时间',
    `request_at`      datetime       DEFAULT NULL COMMENT '请求订单时间',
    `address`         varchar(255)   DEFAULT NULL COMMENT '收款地址',
    `user_id`         int            NOT NULL COMMENT 'partner id',
    `admin_id`        int            DEFAULT NULL COMMENT 'admin id',
    `receipt_image`   BOOLEAN        DEFAULT FALSE COMMENT '是否上传图片',
    `remark`          varchar(255)   DEFAULT NULL COMMENT '註解',
    PRIMARY KEY (`id`) USING BTREE,
    UNIQUE KEY (`serial_number`) USING BTREE,
    INDEX (`user_id`)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_general_ci;

-- 2024-06-07
ALTER TABLE sys_info ADD COLUMN usdt_exchange_status tinyint(1) NOT NULL DEFAULT 0 COMMENT 'usdt开关0停止1开启';
ALTER TABLE sys_info ADD COLUMN usdt_exchange_bonus_rate decimal(14, 4) NOT NULL DEFAULT 0 COMMENT '红利比例';
ALTER TABLE sys_info ADD COLUMN usdt_exchange_rate decimal(14, 4) NOT NULL DEFAULT 0 COMMENT 'usdt费率';
# 添加权限
INSERT INTO `permissions` ( `pid`, `name`, `path`, `type`, `status`) VALUES ( 8, '码商usdt充值订单', '', 0, 1);
INSERT INTO permissions ( pid, name, path, type, status) VALUES (85, '查看/导出', '/usdtRecharge/getUsdtRechargePartner', 1, 1);
INSERT INTO permissions ( pid, name, path, type, status) VALUES ( 85, '确认完成/驳回', '/usdtRecharge/handleUsdtRechargePartner', 1, 1);
# 卡余额限制
ALTER TABLE `payment` ADD COLUMN `balance_limit` decimal(12,4) DEFAULT '0.00' COMMENT '卡余额限制';

# 增加三方代付
CREATE TABLE `third_pay_df` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `mer_id` varchar(45) DEFAULT NULL,
  `mer_key` varchar(450) DEFAULT NULL,
  `pay_url` varchar(450) DEFAULT NULL,
  `pay_name` varchar(45) DEFAULT NULL,
  `pay_name_zh` varchar(45) DEFAULT NULL COMMENT '支付方中文名',
  `channel_code` int(11) DEFAULT NULL COMMENT '网关如901902等',
  `is_self` int(11) DEFAULT '0' COMMENT '供应链是否是自身，默认0不是',
  `is_xiaoshu` int(11) DEFAULT '0' COMMENT '带不带小数，默认0不带\n',
  `notify_ip` varchar(128) DEFAULT NULL COMMENT '回调通知的ip',
  `query_url` varchar(450) DEFAULT NULL COMMENT '查询订单url',
  `status` tinyint(4) DEFAULT NULL,
  `mer_key2` varchar(450) DEFAULT NULL COMMENT '可以放公钥',
  `mer_key3` varchar(2000) DEFAULT NULL COMMENT '可以放私钥',
  `mer_key4` varchar(450) DEFAULT NULL COMMENT '放其他参数',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=63 DEFAULT CHARSET=utf8 COMMENT='第三方代付';
# 代付订单添加三方代付ID
ALTER TABLE `orders_df` ADD COLUMN `otherpay_id` int DEFAULT NULL COMMENT '三方支付ID' AFTER `earn_partner_self`;
-- 2024-06-13 接入第三方代付 AG代付
INSERT INTO `third_pay_df` ( `mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `query_url`) VALUES ('code', 'priKey', 'https://gw08.kakakay.com/api/bank/agentPay/request', 'AGDF', 'AG代付', '1', '0', '0','https://gw08.kakakay.com/api/coin/agentPay/checkOrder');

# 添加权限
INSERT INTO permissions ( pid, name, path, type, status) VALUES (10, '三方代付派单', '/order/handleBatchThirdpay', 1, 1);
# 代付订单添加三方支付ID
ALTER TABLE `orders_df` ADD COLUMN `otherpay_id` int DEFAULT NULL COMMENT '三方支付ID' AFTER `otherpay`;

-- 2024-06-29 接入第三方代付 cubpay
INSERT INTO `third_pay_df` ( `mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `query_url`) VALUES ('CP785862', '3a6c9e4b45f8b9e9230f1fa15c3d745431581c2ac8035abbaa5a571a6420e7b5', 'https://api.cubpay.in/Payout/DoPayout', 'cubpay', 'cubpay代付', '1', '0', '0','https://api.cubpay.in/Payout/PayoutStatus');
# 代付订单添加三方支付的订单号
ALTER TABLE `orders_df` ADD COLUMN `otherpay_code` varchar(100) DEFAULT NULL COMMENT '三方支付的订单号' AFTER `otherpay`;
ALTER TABLE `orders_df` ADD INDEX `otherpay_code`(`otherpay_code`) USING BTREE;
-- 2024-07-01 修改orders_ds表merchant_code排序类型
ALTER TABLE `orders_ds` MODIFY COLUMN `merchant_code` varchar(64) NOT NULL COMMENT '商户订单编号' AFTER `merchant_id`;
ALTER TABLE balance_record ADD COLUMN merchant_code varchar(100) DEFAULT NULL COMMENT '商户的订单号';
ALTER TABLE balance_record ADD INDEX merchant_code(merchant_code) USING BTREE;

-- 2024-06-29 接入第三方代付 wallet
INSERT INTO `third_pay_df` ( `mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `query_url`) VALUES ('', '22jxO6p5t3wKzdjfqRk4BtlvGaEJVs2qnnaomSREHQlFzA5wqVs919wk8iON', 'https://api.walletflow.in/payout/create', 'wallet', 'wallet代付', '1', '0', '0','https://api.walletflow.in/payout/status');
INSERT INTO `third_pay_df` ( `mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `query_url`) VALUES ( 'OSPAY', '6BhXWihxWoRQGFknFzhk4he7cxYO0FpI', 'https://api.happypay777.net/api/v1/third-party/agency-withdraws', 'happypay', 'happypay代付', '1', '0', '1', 'https://api.happypay777.net/api/v1/third-party/withdraw-queries');
-- 2024-07-07 sys_info添加app_info
ALTER TABLE sys_info ADD COLUMN app_info json DEFAULT NULL COMMENT 'app更新信息';
INSERT INTO `permissions` ( `pid`, `name`, `path`, `type`, `status`) VALUES ( 28, 'app设置', '', 0, 1);

-- 2024-07-07 接入第三方代付 haoda
INSERT INTO `third_pay_df` ( `mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `query_url`, `mer_key2`) VALUES ('4K6aYuVsgU5446', '8GtsbgCxDAEa2406050144425446', 'https://kepler.haodapayments.com/api/v1/payout/initiate', 'haoda', 'Haoda代付', '1', '0', '0','https://kepler.haodapayments.com/api/v1/payout/checkstatus', 'socks5://ceshi:ceshi@34.131.66.127:13563');
-- 2024-07-20 接入第三方代付 haoda2
INSERT INTO `third_pay_df` ( `mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `query_url`, `mer_key2`) VALUES ('eBPnDmRhAC5773', 'WRw5U3pHgTvu2407020656595773', 'https://kepler.haodapayments.com/api/v1/payout/initiate', 'haoda2', 'Haoda2代付', '1', '0', '0','https://kepler.haodapayments.com/api/v1/payout/checkstatus', 'socks5://ceshi:ceshi@34.131.209.149:13563');
-- 2024-07-22 接入第三方代付 haoda3
INSERT INTO `third_pay_df` ( `mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `query_url`, `mer_key2`) VALUES ('M5SBrubYPR5838', 'by1rdBqkfwIG2407020608235838', 'https://kepler.haodapayments.com/api/v1/payout/initiate', 'haoda3', 'Haoda3代付', '1', '0', '0','https://kepler.haodapayments.com/api/v1/payout/checkstatus', 'socks5://ceshi:ceshi@34.131.201.121:13563');

-- 2024-07-09 payment 添加channel通道号
ALTER TABLE payment ADD COLUMN channel int default 1001 COMMENT '通道号' AFTER weight;
-- 2024-07-10 payment upi字段可以存储类似upi://pa=** 的长字符串
ALTER TABLE `payment` MODIFY COLUMN `upi` varchar(500)  DEFAULT NULL COMMENT 'UPI'
ALTER TABLE payment ADD COLUMN channel int default 1001 COMMENT '通道号' AFTER weight;
-- 2024-07-10 payment upi字段可以存储类似upi://pa=** 的长字符串
ALTER TABLE `payment` MODIFY COLUMN `upi` varchar(500)  DEFAULT NULL COMMENT 'UPI';
ALTER TABLE `orders_ds` MODIFY COLUMN `upi` varchar(500)  DEFAULT NULL COMMENT 'UPI';
-- 2024-07-18 merchant 添加商户成功率
INSERT INTO `permissions` ( `pid`, `name`, `path`, `type`, `status`) VALUES ( 16, '商户成功率', '/merchant/getmerchantsuccessrate', 0, 1);


-- 2024-07-12 代付优惠sys_info添加字段
ALTER TABLE sys_info ADD COLUMN range_ds json default NULL COMMENT '设定转三方支付代收金额范围';
-- 2024-07-13 permissions添加数据
INSERT INTO permissions ( pid, name, path, type, status) VALUES (28, '代付优惠', '', 0, 1);
-- 2024-07-01 add column utr
ALTER TABLE `orders_df` ADD COLUMN `utr` varchar(64)DEFAULT NULL COMMENT 'UTR';

-- 2024-07-12 代付优惠sys_info添加字段
ALTER TABLE sys_info ADD COLUMN range_ds json default NULL COMMENT '设定转三方支付代收金额范围';

-- 2024-07-18 merchant 添加商户成功率
INSERT INTO `permissions` ( `pid`, `name`, `path`, `type`, `status`) VALUES ( 16, '商户成功率', '/merchant/getmerchantsuccessrate', 0, 1);

-- 2024-07-25 接入第三方代付 king  mer_key2为服务端公钥 mer_key3为客户端私钥
INSERT INTO `third_pay_df` ( `mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `query_url`, `mer_key2`, `mer_key3`)
VALUES ('1235', 'hMFHTdmvkKUnPqQk', 'https://api.kingspay.top/trade/withdraw', 'kingpay', 'King代付', '1', '0', '0','https://api.kingspay.top/trade/withdraw/query',
        'MFwwDQYJKoZIhvcNAQEBBQADSwAwSAJBAL3GnxmCrIIz9Jd0ISejOqCsmgxlDpQi8k9sKa4pHhphgS83YBRHA76VNCqEQjMgK1CQJGVcbKsqHd9mRZCPrSMCAwEAAQ==',
        'MIIBOQIBAAJAZARfxhHDG4Wb2Rmze1VApJVgIUM0htR7u4jN/OdPkjpGmdkE0tDCPbeP8CoPk5EM45meOaarQo66XT0AxQ5vuQIDAQABAkA3FpWt4eCmCwxRIq/R8Z3+SOw+xeZrkSNpoqtabglMz6peVwao1awdN2LnBffpQoB2ZP7dlh1T2YDfPw1Td+blAiEAxCIFPYIkSTKexo7K0Y/LpI/cmKyyc082OX18jvKin/sCIQCCi8nXuh2Baaaj2LlpEZOJ3ayv3GRCNLMggnpvdrZ82wIgH6y+2+ggpBGgwsBc0OtAIBt7rMx3JVgtkatKamuVB/ECID/ZCKYW49loh9T46W3G5+b04UG9w9dRmQ5cYm9jm0sjAiEAiECuRsVtTb3RYevtYsjpMQhRce1HlBjm1i9caxdz/88=');

-- 2024-07-25 create view for payment order summary
CREATE VIEW today_withdraw_order_summary AS
SELECT
    payment_id,
    CAST(DATE_SUB(time_create, INTERVAL 7 HOUR) AS DATE) AS date,
    COUNT(*) as total_orders,
    SUM(CASE WHEN status = 4 THEN 1 ELSE 0 END) as success_orders,
    SUM(CASE WHEN status <> 4 THEN 1 ELSE 0 END) as fail_orders
FROM
    orders_ds
WHERE
    DATE(DATE_SUB(time_create, INTERVAL 7 HOUR)) = CURRENT_DATE
GROUP BY
    payment_id, date;

-- 2024-08-01 drop view for payment order summary
drop view today_withdraw_order_summary;
-- 2024-08-01 create index for balance_record foreign key
create index balance_record_user_id_index on balance_record (user_id);
-- 2024-08-02 接入第三方代付 Razo代付  mer_key2为账户信息中的Account Number
INSERT INTO `third_pay_df` ( `mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `query_url`, `mer_key2`)
VALUES ('rzp_test_W7rjskTEgqBr6E', 'Svt09ECMBdgmiMClVR5LaI2h', 'https://api.razorpay.com/v1/payouts', 'razo', 'Razo代付',
        '1', '0', '0','https://api.razorpay.com/v1/payouts', '2323230025335346');

-- 2024-08-13 接入第三方代付 YDPay代付  可在mer_key2中自行添加所需代理
INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `query_url`)
VALUES ('1036', '2be49c1d-486e-4237-b26a-f3013d17c3ed', 'https://pay.ydpaypay.com/api/v1/payout/created',
        'ydpay', 'YDPay代付', 1, 0, 0, 'https://pay.ydpaypay.com/api/v1/payout/search');
# 20240830 回执单保存处理20240830
ALTER TABLE `orders_df`
ADD COLUMN `debit_account` varchar(64) CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT NULL COMMENT '回执单 转账账号';

-- 2024-08-19 接入第三方代付 sd代付
INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `query_url`)
VALUES ('3769362188636602', 'Z4LpWX2VqJhg20vq', 'https://mapi.indmc.xyz/api/withdraw/create', 'sdpay', 'SDPay代付',
        '1', '0', '0', 'https://mapi.indmc.xyz/api/withdraw/order');

-- 2024-08-21 接入第三方代付 Queen代付
INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `query_url`)
VALUES ('merchant', 'f5c39b21ce3e80ffd10e22a5d53175e5', 'https://ospay.la2568.site/api/daifu', 'queen', 'Queen代付',
        '1', '0', '0', 'https://ospay.la2568.site/api/query');

-- 2024-08-27 接入第三方代付 INPAY代付
INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `query_url`)
VALUES ('20240827160150203', '7e148bfeaf4d7b77d60d5baa098036fb', 'https://inpay.cash/api/v3/withdrawals', 'inpay', 'INPAY代付', '1', '0', '0', 'https://inpay.cash/api/v3/withdrawals/query');

# 2024/8/27 19:32:30 Add 代付改派权限分离 确认，上传凭证，改派，指派 全部分开    旧的方法注释&&备注说明
INSERT INTO `permissions` (`pid`, `name`, `path`, `type`, `status`) VALUES (10, '确认', '/order/HandleOrderdfType1', 1, 1);
INSERT INTO `permissions` (`pid`, `name`, `path`, `type`, `status`) VALUES (10, '上传凭证2', '/order/HandleOrderdfType2', 1, 1);
INSERT INTO `permissions` (`pid`, `name`, `path`, `type`, `status`) VALUES (10, '改派', '/order/HandleOrderdfType3', 1, 1);
INSERT INTO `permissions` (`pid`, `name`, `path`, `type`, `status`) VALUES (10, '指派', '/order/HandleOrderdfType4', 1, 1);
# 原始的 确认，上传凭证，改派，指派权限移除
# 原始数据 81	10	改派/GET/确认	/order/handleorderdf	1	0
UPDATE `permissions` SET `status` = 0 WHERE `id` = 81

# 2024/9/10
ALTER TABLE sys_info ADD COLUMN usdt_received_address LONGTEXT COMMENT 'usdt转入地址';
ALTER TABLE sys_info ADD COLUMN usdt_amount_limit decimal(12, 4) DEFAULT 0 COMMENT 'usdt金额限制';
ALTER TABLE sys_info add `range_df` json DEFAULT NULL COMMENT '设定转三方支付代付金额范围';
ALTER TABLE `ospay`.`payment` ADD INDEX `upi`(`upi`)

-- 2024-09-18 接入第三方代付 添加代付批量上传回执的接口权限sql
INSERT INTO `permissions` (`pid`, `name`, `path`, `type`, `status`) VALUES (10, '批量上传凭证', '/order/uploadreceiptbatch', 1, 1);

-- add-df-limit-setting1002  
ALTER TABLE `merchant` 
ADD COLUMN `amount_fixed` DECIMAL(10, 2) NULL DEFAULT '0.00' COMMENT '代付固定金额';

-- 2024-10-04 添加短信列表权限
INSERT INTO `permissions` (`pid`, `name`, `path`, `type`, `status`) VALUES (19, '短信列表', '', 0, 1);


# 收款资料权限分离 right-separte-1002
INSERT INTO indian.permissions (pid, name, path, type, status) VALUES
(22, '限额', '/partner/updatePaymentLimit', 1, 1),
(22, 'reject', '/partner/updatePaymentReject', 1, 1),
(22, 'pass', '/partner/updatePaymentPass', 1, 1),
(22, '禁用', '/partner/updatePaymentDisenable', 1, 1),
(22, '启用', '/partner/updatePaymentEnable', 1, 1),
(22, '人工锁定', '/partner/updatePaymentLock', 1, 1),
(22, '人工解锁', '/partner/updatePaymentUnlock', 1, 1),
(22, 'correction', '/partner/updatePaymentCorrection', 1, 1),
(22, '普通收款', '/partner/updatePaymentCommon', 1, 1),
(22, '优先收款', '/partner/updatePaymentPri', 1, 1),
(22, '确认编辑', '/partner/updatePaymentEdit', 1, 1);

INSERT INTO `permissions` (`pid`, `name`, `path`, `type`, `status`) VALUES (22, '取消限制', '/partner/cancelLimit', 1, 1);


-- 2024-10-16 接入第三方代付 redpay代付
INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `query_url`)
VALUES ('241027900', '922lbaljls0ixe0l2ac8zq7tqpbd7qgy', 'https://redpay.co.in/Payment_Dfpay_add.html', 'redpay', 'REDPAY代付', '1', '0', '0', 'https://redpay.co.in/Payment_Dfpay_query.html');

-- 2024-10-24 margin-staging-paytm1018 paytm唤醒处理
INSERT INTO  channel (code, name, type, url, rate, rates, amount_min, amount_max, amount_fixed, fixed, status, time_update, time_create) VALUES (1004, 'UPI', 1, '1', 0.0010, '0.003,0.002', 1.00, 50000.00, NULL, 0, 1, '2024-06-27 17:44:49', '2023-10-30 15:46:46');

-- 2024-10-15 角色权限“是否加密”，改为3个独立的权限配置【“禁止查看码商手机号”，“禁止查看数据统计”，“禁止查看代收7日数据统计”】
INSERT INTO `permissions` (`pid`, `name`, `path`, `type`, `status`) VALUES (20, '禁止查看码商手机号', '', 0, 1);
INSERT INTO `permissions` (`pid`, `name`, `path`, `type`, `status`) VALUES (1, '禁止查看数据统计', '', 0, 1);
INSERT INTO `permissions` (`pid`, `name`, `path`, `type`, `status`) VALUES (1, '禁止查看代收7日数据统计', '', 0, 1);

-- 2024-10-23 添加权限
INSERT INTO permissions (pid, name, `path`, `type`, status) VALUES(9, '禁止查看代收订单结算金额', '', 0, 1);
INSERT INTO permissions (pid, name, `path`, `type`, status) VALUES(9, '禁止查看代收订单商户费率', '', 0, 1);
INSERT INTO permissions (pid, name, `path`, `type`, status) VALUES(9, '禁止查看代收订单手续费', '', 0, 1);
INSERT INTO permissions (pid, name, `path`, `type`, status) VALUES(9, '禁止查看代收订单商代盈利', '', 0, 1);
INSERT INTO permissions (pid, name, `path`, `type`, status) VALUES(9, '禁止查看代收订单码商盈利', '', 0, 1);
INSERT INTO permissions (pid, name, `path`, `type`, status) VALUES(9, '禁止查看代收订单平台利润', '', 0, 1);
INSERT INTO permissions (pid, name, `path`, `type`, status) VALUES(10, '禁止查看代付订单结算金额', '', 0, 1);
INSERT INTO permissions (pid, name, `path`, `type`, status) VALUES(10, '禁止查看代付订单商户费率', '', 0, 1);
INSERT INTO permissions (pid, name, `path`, `type`, status) VALUES(10, '禁止查看代付订单手续费', '', 0, 1);
INSERT INTO permissions (pid, name, `path`, `type`, status) VALUES(10, '禁止查看代付订单商代盈利', '', 0, 1);
INSERT INTO permissions (pid, name, `path`, `type`, status) VALUES(10, '禁止查看代付订单码商盈利', '', 0, 1);
INSERT INTO permissions (pid, name, `path`, `type`, status) VALUES(10, '禁止查看代付订单平台利润', '', 0, 1);

-- kakakay 开发1026
INSERT INTO `otherpay` (`merchant_id`, `key`, `key2`, `key3`, `name`, `pay_url`, `channel_code`, `notify_ip`, `query_url`, `forcible`, `status`, `updated`, `created`) VALUES ('code', 'code', 'priKey', '', 'lucky', 'https://gw08.kakakay.com/api/coin/pay/request', 1005, '8.209.248.144,47.245.29.177,8.222.81.208,8.222.76.142', 'https://gw08.kakakay.com/api/coin/pay/checkOrder', 0, 1, '2024-10-26 22:54:22', '2023-12-31 16:39:21');
INSERT INTO `channel` (`code`, `name`, `type`, `url`, `rate`, `rates`, `amount_min`, `amount_max`, `amount_fixed`, `fixed`, `status`, `time_update`, `time_create`) VALUES (1005, 'lucky', 1, '1', 0.0010, '0.003,0.002', 1.00, 50000.00, NULL, 0, 1, '2024-10-26 20:05:41', '2023-10-30 15:46:46');
ALTER TABLE orders_ds
ADD COLUMN third_party_id VARCHAR(64) DEFAULT '',  -- 三方 ID，默认值为空
ADD COLUMN third_party_order_number VARCHAR(64) DEFAULT '',  -- 三方订单号，默认值为空
ADD COLUMN `third_party_name` VARCHAR(64) DEFAULT '' COMMENT 'otherpay的name';  -- 三方，默认值为空

-- 2024-11-01 接入第三方代付 apay代付
INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `query_url`)
VALUES ('RCEO1933', 'px241v0b72w7vsmz', 'https://cashwork.apay.ink/apay/ap.do', 'apay', 'APAY代付', '1', '0', '0', 'https://cashwork.apay.ink/apay/query.do');


-- 2024-11-04 接入第三方代收 apay代收
INSERT INTO `otherpay` (`merchant_id`, `key`, `name`, `pay_url`, `channel_code`, `query_url`)
VALUES ('RCEO1933', 'px241v0b72w7vsmz', 'apay', ' https://cashwork.apay.ink/apay/gateway.do', 1002, 'https://cashwork.apay.ink/apay/query.do');

-- 2024-11-05 一个码同时接多个通道，二维码id可以编辑选择多个通道
ALTER TABLE payment
ADD channel VARCHAR(255) DEFAULT '' COMMENT '支付渠道';

-- add-bmspay-1107 King_Pay 代收开发
INSERT INTO `otherpay` (`merchant_id`, `key`, `key2`, `key3`, `name`, `pay_url`, `channel_code`,
`notify_ip`, `query_url`, `forcible`, `status`, `updated`, `created`) VALUES ( '1235', 'hMFHTdmvkKUnPqQk', 'MFwwDQYJKoZIhvcNAQEBBQADSwAwSAJBAL3GnxmCrIIz9Jd0ISejOqCsmgxlDpQi8k9sKa4pHhphgS83YBRHA76VNCqEQjMgK1CQJGVcbKsqHd9mRZCPrSMCAwEAAQ==', 'MIIBOQIBAAJAZARfxhHDG4Wb2Rmze1VApJVgIUM0htR7u4jN/OdPkjpGmdkE0tDCPbeP8CoPk5EM45meOaarQo66XT0AxQ5vuQIDAQABAkA3FpWt4eCmCwxRIq/R8Z3+SOw+xeZrkSNpoqtabglMz6peVwao1awdN2LnBffpQoB2ZP7dlh1T2YDfPw1Td+blAiEAxCIFPYIkSTKexo7K0Y/LpI/cmKyyc082OX18jvKin/sCIQCCi8nXuh2Baaaj2LlpEZOJ3ayv3GRCNLMggnpvdrZ82wIgH6y+2+ggpBGgwsBc0OtAIBt7rMx3JVgtkatKamuVB/ECID/ZCKYW49loh9T46W3G5+b04UG9w9dRmQ5cYm9jm0sjAiEAiECuRsVtTb3RYevtYsjpMQhRce1HlBjm1i9caxdz/88=', 'kingpay', 'https://api.kingspay.in/trade/preorder', 1006, '65.0.140.172', 'https://api.kingspay.in/trade/order/query', 0, 1, '2024-11-08 17:35:08', '2023-12-31 16:39:21');

INSERT INTO `channel` (`id`, `code`, `name`, `type`, `url`, `rate`, `rates`, `amount_min`, `amount_max`, `amount_fixed`, `fixed`, `status`, `time_update`, `time_create`) VALUES (1006, 'kingpay', 1, '1', 0.0010, '0.003,0.002', 1.00, 50000.00, NULL, 0, 1, '2024-11-10 22:48:52', '2023-10-30 15:46:46');

ALTER TABLE `otherpay`
MODIFY COLUMN `key2` varchar(2000) CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT NULL COMMENT '可以放公钥',
MODIFY COLUMN `key3` varchar(2000) CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT NULL COMMENT '可以放私钥';

-- 商户编号设置1117
ALTER TABLE `sys_info`
ADD COLUMN `merchant_ids` varchar(255) NULL COMMENT '商户编号一栏 逗号分隔';

-- 2024-11-28 码商订单统计
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

-- 2024-11-28 活动相关表
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

-- 增加usdt代付优惠活动设置
ALTER TABLE sys_info ADD COLUMN range_usdt_df json default null AFTER range_ds;

--- 活动相关菜单
INSERT INTO `ospay`.`permissions` (`id`, `pid`, `name`, `path`, `type`, `status`) VALUES (97, 97, '活动中心', '', 0, 1);

INSERT INTO `ospay`.`permissions` (`pid`, `name`, `path`, `type`, `status`) VALUES (97, '活动配置', '', 0, 1);
INSERT INTO `ospay`.`permissions` (`pid`, `name`, `path`, `type`, `status`) VALUES (97, '活动明细配置', '', 0, 1);
INSERT INTO `ospay`.`permissions` (`pid`, `name`, `path`, `type`, `status`) VALUES (97, '活动奖励日志', '', 0, 1);

-- usdt优惠活动设置菜单
INSERT INTO `ospay`.`permissions` (`pid`, `name`, `path`, `type`, `status`) VALUES (28, 'usdt代付优惠', '', 0, 1);

-- 2024-10-18 接入第三方代付 lucky代付  查询地址中携带参数，需在代码请求时填入
INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `query_url`)
VALUES ('code', 'priKey', 'https://gw08.kakakay.com/api/bank/agentPay/request', 'lucky', 'LUCKY代付', '1', '0', '0', 'https://gw08.kakakay.com/api/coin/agentPay/checkOrder?clientCode={clientCode}&clientNo={clientNo}&sign={sign}');

-- 2024-12-12 接入第三方代付 apay代付
INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `query_url`)
VALUES ('CUQO12', 'kvdpsTUfIahVeBWvBHaPsqTHldWMVlKlfByWUAEBeOGtsFwr', 'https://api.for9wqiktyh.com/withdraw/order', 'globe', 'Globe代付', '1', '0', '0', 'https://api.for9wqiktyh.com/withdraw/order/query');

-- 报表开发 add-export-statics1210
INSERT INTO permissions (pid, name, path, type, status) VALUES (8, '码商充值统计', '', 0, 1)
CREATE TABLE `partner_summary`  (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `partner_id` int(11) NULL DEFAULT NULL,
  `formatted_date` date NOT NULL,
  `name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `payoutCount` int(11) NULL DEFAULT 0,
  `payoutSum` decimal(18, 4) NULL DEFAULT 0.0000,
  `usdtCount` int(11) NULL DEFAULT 0,
  `usdtSum` decimal(18, 4) NULL DEFAULT 0.0000,
  `count` int(11) NULL DEFAULT 0,
  `sum` decimal(18, 4) NULL DEFAULT 0.0000,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `idx_partner_date`(`partner_id`, `formatted_date`) USING BTREE
) COMMENT '统计报表用';

-- ----------------------------
-- Table structure for sys_settings
-- ----------------------------
CREATE TABLE `sys_settings`  (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '键名称',
  `value` text CHARACTER SET utf8 COLLATE utf8_general_ci NULL COMMENT '键内容',
  PRIMARY KEY (`id`) USING BTREE
) COMMENT = '系统配置表(报表定义等)';

-- ----------------------------
-- Records of sys_settings
-- ----------------------------
INSERT INTO `sys_settings` VALUES (1, 'partner_statics', '21766,31266,31266');


-- 用户权限开发
ALTER TABLE `roles` 
MODIFY COLUMN `permissions` VARCHAR(2048) CHARACTER SET utf8 COLLATE utf8_general_ci NULL COMMENT '指令权限';


ALTER TABLE `roles` 
ADD COLUMN `level` tinyint(1) NULL DEFAULT 1 COMMENT '级别编号' ;

ALTER TABLE `permissions` 
ADD COLUMN `level` tinyint(1) NULL DEFAULT 1 COMMENT '级别编号' ;

INSERT INTO `permissions` (`pid`, `name`, `path`, `type`, `status`, `level`) VALUES (25, '功能树管理', '', 0, 1, 1)

ALTER TABLE `roles`
ADD COLUMN `admin_id` INT(11) DEFAULT 1 NULL COMMENT '添加的管理员编号';

ALTER TABLE `admin`
ADD COLUMN `admin_id` INT(11) DEFAULT 1 NULL COMMENT '添加的管理员编号';

ALTER TABLE `permissions`
ADD COLUMN `admin_id` INT(11) DEFAULT 1 NULL COMMENT '添加的管理员编号';

-- 2024-12-31 接入第三方代付 rupix代付
INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `query_url`)
VALUES ('6773a42c6f54375f4424ad7a', '1f3d8cfae03847ba8229c02950847e7a', 'https://api.peupay.com/api/merchant/out/create', 'rupix', 'Rupix代付', '1', '0', '0', 'https://api.peupay.com/api/merchant/out/info');

-- 2024-01-25 接入第三方代付 58pay代付
INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `query_url`)
VALUES ('10049', '731C4DD5A5E46123F0BCDEA620296609', 'https://58payapi.tatatapay.com/v1.0/api/order/create', '58pay', '58pay代付', '1', '0', '0', 'https://58payapi.tatatapay.com/v1.0/api/order/query');

-- 2024-01-25 接入第三方代付 快音支付代付
INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `query_url`)
VALUES ('O8x5H3VY', 'FEndJ6sTOolWHwyU', 'https://api.utezf.xyz/payfor/trans', 'kuaiyin', '快音代付', '1', '0', '0', 'https://api.utezf.xyz/payfor/orderquery');

-- 2025-02-23  接入第三方代收 King_Pay
INSERT INTO `otherpay` (`merchant_id`, `key`, `key2`, `key3`, `name`, `pay_url`, `channel_code`, `notify_ip`, `query_url`, `forcible`, `status`)
VALUES ( '1297', 'C8dSBGiqfCP3bcPS', 'MFwwDQYJKoZIhvcNAQEBBQADSwAwSAJBAL3GnxmCrIIz9Jd0ISejOqCsmgxlDpQi8k9sKa4pHhphgS83YBRHA76VNCqEQjMgK1CQJGVcbKsqHd9mRZCPrSMCAwEAAQ==',
        'MIIBVAIBADANBgkqhkiG9w0BAQEFAASCAT4wggE6AgEAAkEA1nBvaVj9eCf/L6HxhJcDsm5Vk0b6ou5jHHkizy9BY4Z2GcdRy8Nwc0CSiPeHSyNZPA3hPqytQ4badEnR5+K1zQIDAQABAkAwQYUQ0/HWREns0iijichPMv0W83YbjEHJeokWzq+MUaA2F5pD9Il6Myq8TZEKaKHfWlzaYHkuuyVaOWsQjaWRAiEA+wg4BxQq1pyAoIknesa5HiQhQAvfzoWgBU1tUm1zIXsCIQDartQ7lqLaJ+fsLRPuYjmNplPfiVxB1jKVLhqMf1pvVwIgEBxQ7DNhJHDa2HK08+45BzQuZhvc+zYcNPrpHzcjAm0CIEMPM7PmOKBPdnZdSGxkoKOIatX0qF7kEXTfw3JsJ05XAiEAwNN1erjms+Or5omQgGKgacf0ACEFu5hjhqT1qjFOum4=',
        'kingpay2', 'https://api.kingspay.in/trade/preorder', 1007, '65.0.140.172', 'https://api.kingspay.in/trade/order/query', 0, 1);
INSERT INTO `channel` (`code`, `name`, `type`, `url`, `rate`, `rates`, `amount_min`, `amount_max`, `amount_fixed`, `fixed`, `status`) VALUES (1007, 'kingpay2', 1, '1', 0.0010, '0.003,0.002', 1.00, 50000.00, NULL, 0, 1);

-- 2025-02-23 接入第三方代付 king  mer_key2为服务端公钥 mer_key3为客户端私钥
INSERT INTO `third_pay_df` ( `mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `query_url`, `mer_key2`, `mer_key3`)
VALUES ('1297', 'C8dSBGiqfCP3bcPS', 'https://api.kingspay.top/trade/withdraw', 'kingpay2', 'King代付2', '1', '0', '0','https://api.kingspay.top/trade/withdraw/query',
        'MFwwDQYJKoZIhvcNAQEBBQADSwAwSAJBAL3GnxmCrIIz9Jd0ISejOqCsmgxlDpQi8k9sKa4pHhphgS83YBRHA76VNCqEQjMgK1CQJGVcbKsqHd9mRZCPrSMCAwEAAQ==',
        'MIIBVAIBADANBgkqhkiG9w0BAQEFAASCAT4wggE6AgEAAkEA1nBvaVj9eCf/L6HxhJcDsm5Vk0b6ou5jHHkizy9BY4Z2GcdRy8Nwc0CSiPeHSyNZPA3hPqytQ4badEnR5+K1zQIDAQABAkAwQYUQ0/HWREns0iijichPMv0W83YbjEHJeokWzq+MUaA2F5pD9Il6Myq8TZEKaKHfWlzaYHkuuyVaOWsQjaWRAiEA+wg4BxQq1pyAoIknesa5HiQhQAvfzoWgBU1tUm1zIXsCIQDartQ7lqLaJ+fsLRPuYjmNplPfiVxB1jKVLhqMf1pvVwIgEBxQ7DNhJHDa2HK08+45BzQuZhvc+zYcNPrpHzcjAm0CIEMPM7PmOKBPdnZdSGxkoKOIatX0qF7kEXTfw3JsJ05XAiEAwNN1erjms+Or5omQgGKgacf0ACEFu5hjhqT1qjFOum4=');

-- 2024-02-26 接入第三方代付 Wepay对接(代收代付)
INSERT INTO `otherpay` (`merchant_id`, `key`, `key2`, `key3`, `name`, `pay_url`, `channel_code`, `notify_ip`,
`query_url`, `forcible`, `status`, `updated`, `created`)
VALUES ('999100111', '04e1266332d24d428e9ee6400d6da643', NULL, NULL, 'wepay', 'https://api.wepayglobal.com/pay/web', 1007, '52.76.11.7', 'https://api.wepayglobal.com/query/order', 0, 1, '2025-02-25 19:54:33', '2023-12-31 16:39:21');

INSERT INTO `channel` (`code`, `name`, `type`, `url`, `rate`, `rates`, `amount_min`, `amount_max`, `amount_fixed`,
`fixed`, `status`, `time_update`, `time_create`)
VALUES (1007, 'weepay', 1, '1', 1.0000, '1', 1.00, 10000.00, NULL, 0, 1, '2025-02-25 18:18:13', '2025-02-25 18:16:52');

INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`,
`is_xiaoshu`, `notify_ip`, `query_url`, `status`, `mer_key2`, `mer_key3`, `mer_key4`)
VALUES ('999100111', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'https://api.wepayglobal.com/pay/transfer', 'wepay', 'wepay支付', NULL, 0, 0, '52.76.11.7', 'https://api.wepayglobal.com/query/transfer', 1, NULL, NULL, NULL);

-- 2024-03-03 接入第三方代付 lemon对接(代付:https://payment.ydgj1688.com/Payment)
INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `notify_ip`, `query_url`, `status`, `mer_key2`, `mer_key3`, `mer_key4`) VALUES ('1000099', 'e06e65c8061ef0ab254feb71bcfd3431', 'https://payment.ydgj1688.com/Payment', 'lemonpay', 'lemon支付', NULL, 0, 0, '47.245.107.163', 'https://payment.ydgj1688.com/Look/payment_order', 1, NULL, NULL, NULL);

-- 2024-03-05 接入第三方代付 777pay
INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `notify_ip`, `query_url`, `status`, `mer_key2`, `mer_key3`, `mer_key4`)
VALUES ('f18a52b5e2cb4053881b96d69c5a02ac', 'MgzeL5Q3YoUGr8NzTSdKKQxCbUU3NalirqHFwB', 'https://www.777-pay.com/open-api/create-payout-order', 'pay777pay', '777pay支付', NULL, 0, 0, '13.212.204.110', 'https://www.777-pay.com/open-api/query-payout-order', 1, NULL, NULL, NULL);

-- 2024-03-06 接入第三方代收 777pay
INSERT INTO `otherpay` (`merchant_id`, `key`, `name`, `pay_url`, `channel_code`, `query_url`)
VALUES ('f18a52b5e2cb4053881b96d69c5a02ac', 'MgzeL5Q3YoUGr8NzTSdKKQxCbUU3NalirqHFwB', '777pay', 'https://www.777-pay.com/open-api/create-pay-order', 1008, 'https://www.777-pay.com/open-api/query-pay-order');
INSERT INTO `channel` (`code`, `name`, `type`, `url`, `rate`, `rates`, `amount_min`, `amount_max`, `amount_fixed`, `fixed`, `status`) VALUES (1008, '777pay', 1, '1', 0.0010, '0.003,0.002', 1.00, 50000.00, NULL, 0, 1);

-- 2024-03-08 接入第三方代收 SwiftPay  key2 公钥  key3 私钥
INSERT INTO `otherpay` (`merchant_id`, `key`, `key2`, `key3`, `name`, `pay_url`, `channel_code`, `query_url`)
VALUES ('SOspay', '',
        'MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArHjQ3i93MhwbqTlO4w/G/g4MHpP0ePbEhYbJp75ZZNpVDZuoIO9VNz56GO6x7jFGPeY4J+3mTZGjjSIuRICejmzUTiZJYM6JMjLx38Bf/+GMd1lxEq2ktA1R6ClUUDLMwaII6Wdl/QbaSe7aSeBChLXCdOaQuFpZ0F+Kz2z9o2x1zdx00Y0hhY5qvlOVKL8CO1RA8LjC847golExRaZFwIjoT9t/7uT76j2brZAKL9prLaYqWKoQTSXdfFhXqIVHtCV2BhYVr/kqM+gVtO7vxX9elUbObIw/hSHHPPtaV8rOMx+QoVku0H2RUCmPNSxpqlxPUHz6zbJJ3vVuTa6lWwIDAQAB',
        'MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQCXInSK8iV0+p138rEZuFIo+tZRGmmpKh484B1PQ5pbQ2Zw9Ec7x9ZMhW6SxQfMDjWjSJqsMNMNChvUj9j5+57BnmOD9Y1AzwwoOkKr+0Jauet1juRcRiz23KS9zMFu6Y1JouZso7Ybj+UuhCrciNyGjZHzqCq0H093Sy2yYMvohwDZFC2c6741kk1wcRuMczLAM7ajXf8wdMokwDw3NtU2rr8U8tpdBLd+9pi870tEOLymw0Yspw2jrEsXi+NQQIXj7//OzpN7FI8+hlYCZiv8ryaQh4N+9Mqot7hCRVM+25Wi5re7VvXyKBAsYDtIGFVUVjRl3VE1B2Ssi4Wqce6pAgMBAAECggEAYJRMFV6YQSDF8BjOw7jeCAIDYuCWFNwtZolxMW3p/dgcZqIzwyf48f1yo6f1S5jo/ecvsEmjFPoYvsUNyvHYibJFtdX85iVph2tzn6N4y7FznjQqCi1uHnLxc7idA9uLxjqrNVGI1iQmOIuNOFDdW76sPiCA6Yn4pisMkKj6pSRemJLGy3ZqjD2R9hQO0gHhCT6XIAqnXMKBuWJS5M14DigIvItMNSPkKRisMcPDc1L5KwgpsB9jYfQgUBGild8uv91BgV36qrqnphLffem0fFdichzZ6QixqfeiQ2LB5Z9i217/Flr88Vcwrl4E6+M+XeIogudno+bdOnFBGzJx4QKBgQD3E3LM/r1C5mxhHRTvr+8X1Z7LUV1RGMXZjgFmorDg6VLOAXrORyXW6/zA8LDcgXeDvrSV12AqohrvfqtCekS/zZ8MVWIE5i6JaUKCNsMYfIEziQVGRdYM7XL6sr9WfBg4ULZEQSWPGQiJcuoL15Zy+nBJBzZ+40Vfwy9l4RPHpwKBgQCcl+YjD7+JOtpuFpZiGukE/UOw/TJFGrQueXo/gaUftGTyRUZoT6v2c5m4C7fr21AiYAFCyq7hCrclGFoh8G2vsjCq6agLquuuS3Hbz34wj2nDcFuuGdskgaeLd4fpPyk5Q4Hn+iflCWmmFdhDCZGE2CiuEKdxFS2MBM2N4sZhLwKBgQDYi9wfHNkF7GxqxRFXbYwRCLIvInW2IQ8uuM4zhT2fMf/X++YFKshYUOZqt8laycHU3uzpMyXe18rhwtQY5I6iyHWwWpkZECETYAThmVtud5jJcTsFNyn+lJIkdUtLYmHb4amNssdXXqpjxSqqDF6ZETQeXUr+9PQVlT1Sfm1WmwKBgCi8l2D9os03Y0WKWLrS11W18Rsk8yPpC4Cfl37X4jX6PtyLywIt38VwU0f+vGz+E72tjgZrJc1jdTuQNzpnCpHPYDvGJzJJ15/y/n65XtGRLWlrXF5RWaIInKZ6hP/Xr4i3GB9aA3Dg3vwW6Lifz5xog0StDnIrmTq4sSS9HvB/AoGALMlYVgl/4i/KLIGq46iPaEsYN4u4+2tWYTO0JCktAlviXQ904xDBdHWMhb/qwbbDNxrNE8FJbsAQCumXGyPzZWcynqwa9traEqUP0Xvq/NrpcK9d5zVsT6ZadGQdHvlbgQiSAAa3kolKGo1raHpLs/nZST1CcmjAmMznnjbHc1o=',
        'swiftpay', 'https://api.paymentapi360.com/api/order/createorder', 1009, 'https://api.paymentapi360.com/api/order/checkorder');
INSERT INTO `channel` (`code`, `name`, `type`, `url`, `rate`, `rates`, `amount_min`, `amount_max`, `amount_fixed`, `fixed`, `status`) VALUES (1009, 'swiftpay', 1, '1', 0.0010, '0.003,0.002', 1.00, 50000.00, NULL, 0, 1);

-- 2024-03-09 接入第三方代付 SwiftPay  mer_key2 公钥  mer_key3 私钥
INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `notify_ip`, `query_url`, `status`, `mer_key2`, `mer_key3`)
VALUES ('SOspay', '', 'https://api.paymentapi360.com/api/payout/create', 'swiftpay', 'SwiftPay支付', NULL, 0, 0, '15.207.236.68', 'https://api.paymentapi360.com/api/payout/check', 1,
        'MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArHjQ3i93MhwbqTlO4w/G/g4MHpP0ePbEhYbJp75ZZNpVDZuoIO9VNz56GO6x7jFGPeY4J+3mTZGjjSIuRICejmzUTiZJYM6JMjLx38Bf/+GMd1lxEq2ktA1R6ClUUDLMwaII6Wdl/QbaSe7aSeBChLXCdOaQuFpZ0F+Kz2z9o2x1zdx00Y0hhY5qvlOVKL8CO1RA8LjC847golExRaZFwIjoT9t/7uT76j2brZAKL9prLaYqWKoQTSXdfFhXqIVHtCV2BhYVr/kqM+gVtO7vxX9elUbObIw/hSHHPPtaV8rOMx+QoVku0H2RUCmPNSxpqlxPUHz6zbJJ3vVuTa6lWwIDAQAB',
        'MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQCXInSK8iV0+p138rEZuFIo+tZRGmmpKh484B1PQ5pbQ2Zw9Ec7x9ZMhW6SxQfMDjWjSJqsMNMNChvUj9j5+57BnmOD9Y1AzwwoOkKr+0Jauet1juRcRiz23KS9zMFu6Y1JouZso7Ybj+UuhCrciNyGjZHzqCq0H093Sy2yYMvohwDZFC2c6741kk1wcRuMczLAM7ajXf8wdMokwDw3NtU2rr8U8tpdBLd+9pi870tEOLymw0Yspw2jrEsXi+NQQIXj7//OzpN7FI8+hlYCZiv8ryaQh4N+9Mqot7hCRVM+25Wi5re7VvXyKBAsYDtIGFVUVjRl3VE1B2Ssi4Wqce6pAgMBAAECggEAYJRMFV6YQSDF8BjOw7jeCAIDYuCWFNwtZolxMW3p/dgcZqIzwyf48f1yo6f1S5jo/ecvsEmjFPoYvsUNyvHYibJFtdX85iVph2tzn6N4y7FznjQqCi1uHnLxc7idA9uLxjqrNVGI1iQmOIuNOFDdW76sPiCA6Yn4pisMkKj6pSRemJLGy3ZqjD2R9hQO0gHhCT6XIAqnXMKBuWJS5M14DigIvItMNSPkKRisMcPDc1L5KwgpsB9jYfQgUBGild8uv91BgV36qrqnphLffem0fFdichzZ6QixqfeiQ2LB5Z9i217/Flr88Vcwrl4E6+M+XeIogudno+bdOnFBGzJx4QKBgQD3E3LM/r1C5mxhHRTvr+8X1Z7LUV1RGMXZjgFmorDg6VLOAXrORyXW6/zA8LDcgXeDvrSV12AqohrvfqtCekS/zZ8MVWIE5i6JaUKCNsMYfIEziQVGRdYM7XL6sr9WfBg4ULZEQSWPGQiJcuoL15Zy+nBJBzZ+40Vfwy9l4RPHpwKBgQCcl+YjD7+JOtpuFpZiGukE/UOw/TJFGrQueXo/gaUftGTyRUZoT6v2c5m4C7fr21AiYAFCyq7hCrclGFoh8G2vsjCq6agLquuuS3Hbz34wj2nDcFuuGdskgaeLd4fpPyk5Q4Hn+iflCWmmFdhDCZGE2CiuEKdxFS2MBM2N4sZhLwKBgQDYi9wfHNkF7GxqxRFXbYwRCLIvInW2IQ8uuM4zhT2fMf/X++YFKshYUOZqt8laycHU3uzpMyXe18rhwtQY5I6iyHWwWpkZECETYAThmVtud5jJcTsFNyn+lJIkdUtLYmHb4amNssdXXqpjxSqqDF6ZETQeXUr+9PQVlT1Sfm1WmwKBgCi8l2D9os03Y0WKWLrS11W18Rsk8yPpC4Cfl37X4jX6PtyLywIt38VwU0f+vGz+E72tjgZrJc1jdTuQNzpnCpHPYDvGJzJJ15/y/n65XtGRLWlrXF5RWaIInKZ6hP/Xr4i3GB9aA3Dg3vwW6Lifz5xog0StDnIrmTq4sSS9HvB/AoGALMlYVgl/4i/KLIGq46iPaEsYN4u4+2tWYTO0JCktAlviXQ904xDBdHWMhb/qwbbDNxrNE8FJbsAQCumXGyPzZWcynqwa9traEqUP0Xvq/NrpcK9d5zVsT6ZadGQdHvlbgQiSAAa3kolKGo1raHpLs/nZST1CcmjAmMznnjbHc1o=');

-- 2024-03-10 商户代收条件限制追加
ALTER TABLE `merchant` 
ADD COLUMN `ds_on` tinyint(1) NULL DEFAULT 1 COMMENT '0/1 开启/关闭(代收黑名单)';

ALTER TABLE `merchant` 
ADD COLUMN `ds_black_ips` varchar(1000) NULL COMMENT '代收黑名单';

ALTER TABLE `merchant` 
ADD COLUMN `ds_userid_on` tinyint(1) NULL DEFAULT 1 COMMENT '0/1 开启/关闭(代收user_id黑名单)';

ALTER TABLE `merchant` 
ADD COLUMN `ds_black_userids` varchar(1000) NULL COMMENT '代收user_id黑名单';

ALTER TABLE `orders_ds` 
ADD COLUMN `user_id` varchar(64) NULL COMMENT 'user_id';

-- 2025-03-18 接入第三方代付 lemonpay2  mer_key2 公钥  mer_key3 私钥
INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `notify_ip`, `query_url`, `status`, `mer_key2`, `mer_key3`, `mer_key4`)
VALUES ('120000', '', 'https://api.lemonpay.top/open/api/order/out', 'lemonpay2', 'Lemon支付2', NULL, 0, 0, '13.212.204.110', 'https://api.lemonpay.top/open/api/order/query/out', 1,
        'MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC4jfnMpUzP9Ujh+9o+p9Wf4zeAgM9eXIAiuc11yHBaV6yPahe8NhXfV7mQXChluQmse5SOr204NOsC0QWmcihI2bI8VQm2R1asmW0dRYBCxfpMMdrCiXM/PaPS9iQ6mX2dl2UBeYTp/w7k7yxeZzZoK3qx5a5gso24B3WwBySyGQIDAQAB',
        'MIICdgIBADANBgkqhkiG9w0BAQEFAASCAmAwggJcAgEAAoGBAJuwwo8Vx24wgAYRWpwzag4mHrPpxF1MQspwQaNmASt4SAGrFlxM6uliaRcCVNJPH9R9HZXj20I67U1yrlbByJT5BIs3RutIutD6qoL+n2b6dfjGfYkznrcsIQXqM+zbRcvEjoDMimb7JnaDA8ZV3uWHVS3KI5kWlc/iGiHZTw5ZAgMBAAECgYAJ2Rz9cwm56Rx4Bcn+/muTeIrRo5RVuHizGHW2ccHaL5ISdPGFpiHn4F84Yt/dq76eMMnZzN92KYcQMpRfjYNz+5Psa2V1JO4K/Dj/KB5ooDw8Yl6YjHft0kvyOvYcFx9Pw6KSd2aLZZu3BJka2EJ53SA1JkvFoasEFy8DqH0gwQJBANhOlAp1rPZCx5SEgBg5jMVAbbD4HAfthODnVcacZDol5XLKfkgCu4srAPKfi2TdtKCeEbTF40/jmVxlsrR1cZECQQC4QpwZdxSdTYZHjPZTc2xO6EBLN58v7HZNNz9CSxw8wADQphV6Tx2kOBANb2lD27rSZNY1e5p0Lx/wYLydIOxJAkEAnDDpb0AXu97utIyU3mk3//sM+fu+ae8VwzzoUDj/molgzGnxk9f9Snmr/oY8JoJ8+noJeQpnoHlNdU2uI+amMQJAGG08JGQU54WPd4zIWufCQ/OmElKdV80RIcthJ3itlaAee4qI7l3uoAaOmjlayxQmAB4+B3kLULuukD9CwdHLgQJALbaKmuZDTlBZM8geR/au/Owj64alINhPE2/WmHPOCIiTEnozM8+FdIOPpeNlOqtLPP+exWjRyf3I9Rw+C1senQ==',
        NULL);

-- 2025-3-17 QuickPay代付接入
ALTER TABLE `third_pay_df`
MODIFY COLUMN `mer_key3` varchar(2000);
INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `notify_ip`, `query_url`, `status`, `mer_key2`, `mer_key3`, `mer_key4`) VALUES ('QOSpaypayout', 'QOSpaypayout', 'https://api.paymentapi111.com/api/payout/create', 'quickpay', 'quickpay支付', NULL, 0, 0, '3.111.140.131, 3.7.70.47', 'https://api.paymentapi111.com/api/payout/check', 1, 'MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArHjQ3i93MhwbqTlO4w/G\r\n/g4MHpP0ePbEhYbJp75ZZNpVDZuoIO9VNz56GO6x7jFGPeY4J+3mTZGjjSIuRICe\r\njmzUTiZJYM6JMjLx38Bf/+GMd1lxEq2ktA1R6ClUUDLMwaII6Wdl/QbaSe7aSeBC\r\nhLXCdOaQuFpZ0F+Kz2z9o2x1zdx00Y0hhY5qvlOVKL8CO1RA8LjC847golExRaZF\r\nwIjoT9t/7uT76j2brZAKL9prLaYqWKoQTSXdfFhXqIVHtCV2BhYVr/kqM+gVtO7v\r\nxX9elUbObIw/hSHHPPtaV8rOMx+QoVku0H2RUCmPNSxpqlxPUHz6zbJJ3vVuTa6l\r\nWwIDAQAB', 'MIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEAAoIBAQDGepisXyBsrymM\r\nLOs5JtGMzJOnsgMTfT0/0ofjhxYosALwxoeUzJHs47k5F5Lj3Dkh1aShD0hsFJ9b\r\nQVZZQdTuH7VWf1C1BltMhKPuAPXlsSRNlkuQjmuydhXDLu5omakJXbxskMroBDJa\r\nZyf4M+rocnPHyd5Bu4cj4fo2r0dWYBuca8EizcXblQpDhCydvu8xqPnDk5rZc4Rb\r\nkrQ8pCS/QLnZiBwRFQ+H5O2OmUFrupRVGNRj8or+MtEtbDKUUzpt5XFClLH+6HLh\r\nNZuTOh7WZtimSxz5N1hHJTXE2eMW9WR1FFgcPKVjgc4AE9+N9yD6Arln516HM5A+\r\neXZjA7OBAgMBAAECggEAQ2iLxa8hIghzgeoXkXd/n+QzGbc5mDrmvHBSOpI8kmEE\r\n/qVOktjPjrbgx2UcPEslFDqtCQ5ZuGtgm+ua2gGjwaP/QHtI+9JG27wIuOKWoQYC\r\noF81FsloBlpYlcuwqNHXORkez3h1kUsrlsyGJKPtWjjU3bvPwl9gTG2JP11USx8L\r\nx67hKB5x8CBo4harF31Z2D+XLJwWvFZnMvRguzPQ2J1ot+LjiR1t3lbO+WH9egvo\r\nVBZlzr6hwse1WPl+4s03V3uglN7PJ2Wlr8eVf6GGnvBGmb4dqWt1ZAXqSpUF/pQq\r\n0O/UpG6/LArcoGGrI0qUiQBRWQ7o5Bsr290i0jwKaQKBgQDqO2VcnPjRGAoEpCl2\r\nQ4SMPNB2p03XA4OVkFO47W+3nTJDGzox8CNYFszqsFi4taEJvL2vvvqdcpRQlWOb\r\nvWOtkhx9Jw9+8OoCqlhj/3FS2N6Vtb3FiidmLoiy6aDsgY4WA/46IAmc8BzW7j3E\r\npzW1iZl/aPrJHt/FxgqKGzKN+wKBgQDY7Jlw4wthZngUM1xPFx+Sn4jEe4lJRV+e\r\nFXtAyH4+BJwZy+dT9x0com1n9skAMDTjOcJte04XWTnLOwu+Ap4AyRKKDuAtBogf\r\nIq0IwJUVUYdeopBWueDHwO6a6WZ02fk4n0q60Pvae1R8v6SzQxHXDUIp2tpAN0Li\r\nVera5cS3swKBgG0ynZGsmI8aTulVAwNgfLXIUENQwghAWiLq8y0efFu0jE8erWXE\r\nlyWlE4lCB0qtWlMoy6HYPgwS87QRwStFAuhTWra59A5xEBeIBMcxukouUq6m2L70\r\nJmQLw6ztIBnCWFRJLkc40mJ4ymklDmTUs0RbztTIQ0pp+1a/egBip5HrAoGATh4+\r\nT7Hj2kqdeaDZYD4Sh6neBev7D6DlAzf3L+hD1i+wy3VrtAgsurAfuC3eSqwRj7aw\r\nNt8Ny0i9kFuOKfolTmEaxQ8AWhadFKFXMOyxg4DdwA3I7wJ3WVg4VR8yX2hT4Lk0\r\nnzw9RnvdfCNDu66ukQRcTFhc+n0sH/gS4IuYIRMCgYB/95vcKT7w2Wj44LUo9ROY\r\nqoE02k0lUxxhn30NDcfylKAEBzTPo5fqQjxwFuGqcxGiuiou7upha/JA5xwL/4rQ\r\nwJXQENM6f6Ujl1z+qb49JwgKGPxdVa7jZd5KqjYdkfqpqeycvkN0hc5rsZBtABNx\r\nyUwbbG3qygqZ0bX++E1sqg==', NULL);

-- 2024-03-20 接入第三方代收 quickpay
INSERT INTO `otherpay` (`merchant_id`, `key`, `key2`, `key3`, `name`, `pay_url`, `channel_code`, `notify_ip`, `query_url`, `forcible`, `status`, `updated`, `created`) VALUES ('QOSpaypayout', 'QOSpaypayout', 'MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArHjQ3i93MhwbqTlO4w/G\r\n/g4MHpP0ePbEhYbJp75ZZNpVDZuoIO9VNz56GO6x7jFGPeY4J+3mTZGjjSIuRICe\r\njmzUTiZJYM6JMjLx38Bf/+GMd1lxEq2ktA1R6ClUUDLMwaII6Wdl/QbaSe7aSeBC\r\nhLXCdOaQuFpZ0F+Kz2z9o2x1zdx00Y0hhY5qvlOVKL8CO1RA8LjC847golExRaZF\r\nwIjoT9t/7uT76j2brZAKL9prLaYqWKoQTSXdfFhXqIVHtCV2BhYVr/kqM+gVtO7v\r\nxX9elUbObIw/hSHHPPtaV8rOMx+QoVku0H2RUCmPNSxpqlxPUHz6zbJJ3vVuTa6l\r\nWwIDAQAB', 'MIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEAAoIBAQDGepisXyBsrymM\r\nLOs5JtGMzJOnsgMTfT0/0ofjhxYosALwxoeUzJHs47k5F5Lj3Dkh1aShD0hsFJ9b\r\nQVZZQdTuH7VWf1C1BltMhKPuAPXlsSRNlkuQjmuydhXDLu5omakJXbxskMroBDJa\r\nZyf4M+rocnPHyd5Bu4cj4fo2r0dWYBuca8EizcXblQpDhCydvu8xqPnDk5rZc4Rb\r\nkrQ8pCS/QLnZiBwRFQ+H5O2OmUFrupRVGNRj8or+MtEtbDKUUzpt5XFClLH+6HLh\r\nNZuTOh7WZtimSxz5N1hHJTXE2eMW9WR1FFgcPKVjgc4AE9+N9yD6Arln516HM5A+\r\neXZjA7OBAgMBAAECggEAQ2iLxa8hIghzgeoXkXd/n+QzGbc5mDrmvHBSOpI8kmEE\r\n/qVOktjPjrbgx2UcPEslFDqtCQ5ZuGtgm+ua2gGjwaP/QHtI+9JG27wIuOKWoQYC\r\noF81FsloBlpYlcuwqNHXORkez3h1kUsrlsyGJKPtWjjU3bvPwl9gTG2JP11USx8L\r\nx67hKB5x8CBo4harF31Z2D+XLJwWvFZnMvRguzPQ2J1ot+LjiR1t3lbO+WH9egvo\r\nVBZlzr6hwse1WPl+4s03V3uglN7PJ2Wlr8eVf6GGnvBGmb4dqWt1ZAXqSpUF/pQq\r\n0O/UpG6/LArcoGGrI0qUiQBRWQ7o5Bsr290i0jwKaQKBgQDqO2VcnPjRGAoEpCl2\r\nQ4SMPNB2p03XA4OVkFO47W+3nTJDGzox8CNYFszqsFi4taEJvL2vvvqdcpRQlWOb\r\nvWOtkhx9Jw9+8OoCqlhj/3FS2N6Vtb3FiidmLoiy6aDsgY4WA/46IAmc8BzW7j3E\r\npzW1iZl/aPrJHt/FxgqKGzKN+wKBgQDY7Jlw4wthZngUM1xPFx+Sn4jEe4lJRV+e\r\nFXtAyH4+BJwZy+dT9x0com1n9skAMDTjOcJte04XWTnLOwu+Ap4AyRKKDuAtBogf\r\nIq0IwJUVUYdeopBWueDHwO6a6WZ02fk4n0q60Pvae1R8v6SzQxHXDUIp2tpAN0Li\r\nVera5cS3swKBgG0ynZGsmI8aTulVAwNgfLXIUENQwghAWiLq8y0efFu0jE8erWXE\r\nlyWlE4lCB0qtWlMoy6HYPgwS87QRwStFAuhTWra59A5xEBeIBMcxukouUq6m2L70\r\nJmQLw6ztIBnCWFRJLkc40mJ4ymklDmTUs0RbztTIQ0pp+1a/egBip5HrAoGATh4+\r\nT7Hj2kqdeaDZYD4Sh6neBev7D6DlAzf3L+hD1i+wy3VrtAgsurAfuC3eSqwRj7aw\r\nNt8Ny0i9kFuOKfolTmEaxQ8AWhadFKFXMOyxg4DdwA3I7wJ3WVg4VR8yX2hT4Lk0\r\nnzw9RnvdfCNDu66ukQRcTFhc+n0sH/gS4IuYIRMCgYB/95vcKT7w2Wj44LUo9ROY\r\nqoE02k0lUxxhn30NDcfylKAEBzTPo5fqQjxwFuGqcxGiuiou7upha/JA5xwL/4rQ\r\nwJXQENM6f6Ujl1z+qb49JwgKGPxdVa7jZd5KqjYdkfqpqeycvkN0hc5rsZBtABNx\r\nyUwbbG3qygqZ0bX++E1sqg==', 'quickpay', 'https://api.paymentapi111.com/api/order/createorder', 1009, '3.111.140.131, 3.7.70.47', 'https://api.paymentapi111.com/api/order/checkorder', 0, 1, '2025-03-20 11:31:20', '2023-12-31 16:39:21');
INSERT INTO `channel` (`code`, `name`, `type`, `url`, `rate`, `rates`, `amount_min`, `amount_max`, `amount_fixed`, `fixed`, `status`, `time_update`, `time_create`) VALUES (1009, 'quickpay', 1, '1', 0.0010, '0.003,0.002', 1.00, 50000.00, NULL, 0, 1, '2025-03-20 11:29:53', '2023-10-30 15:46:46');


-- 2025-03-19 接入第三方代付 snakepay
INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `notify_ip`, `query_url`, `status`)
VALUES ('139', 'Y7PjNhjrhUuGyvBVso1qdULcNiBA7kpd', 'https://api.snakepay.live/api/v1/payOut/create', 'snakepay', 'Snake支付', 1, 0, 0, '34.47.251.111', 'https://api.snakepay.live/api/v1/utr/query', 1);

-- 2025-03-19 接入第三方代收 snakepay
INSERT INTO `otherpay` (`merchant_id`, `key`, `name`, `pay_url`, `channel_code`, `query_url`)
VALUES ('139', 'Y7PjNhjrhUuGyvBVso1qdULcNiBA7kpd', 'snakepay', 'https://api.snakepay.live/api/v1/payIn/create', 1001, 'https://api.snakepay.live/api/v1/utr/query');

-- 2025-03-23 接入第三方代收+代付 hkpay
INSERT INTO `otherpay` (`merchant_id`, `key`, `key2`, `key3`, `name`, `pay_url`, `channel_code`, `notify_ip`, `query_url`, `forcible`, `status`, `updated`, `created`) VALUES ('711000732', '959DFBCC4562FF0B5580508419C704A2', NULL, NULL, 'hkpay', 'https://api.hhpayapi.com/mcapi/prepaidorder/v2', 1007, '47.237.111.183, 47.237.70.151, 47.237.89.12, 8.219.2.7, 8.219.232.67', 'https://api.hhpayapi.com/mcapi/query', 0, 1, '2025-03-23 18:25:36', '2023-12-31 16:39:21');
INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `notify_ip`, `query_url`, `status`, `mer_key2`, `mer_key3`, `mer_key4`) VALUES ('711000732', '959DFBCC4562FF0B5580508419C704A2', 'https://api.hhpayapi.com/mcapi/prepaidpayorder', 'hkpay', 'hkpay支付', NULL, 0, 0, '47.237.111.183, 47.237.70.151, 47.237.89.12, 8.219.2.7, 8.219.232.67', 'https://api.hhpayapi.com/mcapi/query', 1, NULL, NULL, NULL);

-- 20250407 skpay代收代付重新开发
INSERT INTO `otherpay` (`merchant_id`, `key`, `key2`, `key3`, `name`, `pay_url`, `channel_code`, `notify_ip`, `query_url`, `forcible`, `status`, `updated`, `created`) VALUES ('MP20250000000000028', 'PZc0E6Eagd2efwx4MHUuVT17ZysAJy34', '', 'a6xXNFVqPsbKp9WXmC11BHMZ', 'skpay', 'https://api.skpay.app/mcapi/receive/create', 1088, '34.100.170.21,34.100.203.78', 'https://api.skpay.app/mcapi/receive/query', 0, 1, '2025-04-07 23:25:38', '2025-04-02 16:39:21');
INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `notify_ip`, `query_url`, `status`, `mer_key2`, `mer_key3`, `mer_key4`) VALUES ('MP20250000000000028', 'PZc0E6Eagd2efwx4MHUuVT17ZysAJy34', 'https://api.skpay.app/mcapi/send/create', 'skpay', 'skpay支付', NULL, 0, 0, '34.100.170.21,34.100.203.78', 'https://api.skpay.app/mcapi/send/query', 1, '', 'a6xXNFVqPsbKp9WXmC11BHMZ', NULL);

-- 2025-04-17 接入第三方代付 catspay代付
INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `notify_ip`, `query_url`, `status`)
VALUES ('1000831', 'ab8c48b7024b41d9b4e71b703baa9a24', 'https://api.catspay.top/apinow/withdraw.ashx', 'catspay', 'catspay支付', 1, 0, 0, '47.243.24.93', 'https://api.catspay.top/apinow/withdrawquery.ashx', 1);

-- 2025-04-30 添加后台商户支付链接设置表
CREATE TABLE `merchant_pay_links` (
    `id` int NOT NULL AUTO_INCREMENT COMMENT 'ID',
	`pay_name` VARCHAR(50) NOT NULL,
	`pay_link` VARCHAR(512) NOT NULL,
  PRIMARY KEY (`id`)
) COMMENT='后台商户支付链接';

-- 2025-04-30 添加后台页面商户支付链接页面展示权限
INSERT INTO `permissions` (`pid`, `name`, `path`, `type`, `status`, `level`, `admin_id`) VALUES (28, '商户支付链接设置', '', 0, 1, 1, 1);
INSERT INTO `permissions` (`pid`, `name`, `path`, `level`) VALUES (28, '商户支付链接设置接口', '/setting/MerchantPayLinks', '2');

-- 2025-05-07 接入第三方代付 lemonpay3代付
INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `notify_ip`, `query_url`, `status`)
VALUES ('1810', 'YLhftLWsUtiW5wghHOD3tZ3T', 'https://init.lemonpay.cc/api/agentpay/apply', 'lemonpay3', 'Lemonpay3支付', NULL, 0, 0, '45.135.48.55,8.209.197.176,164.155.29.82,165.154.199.130,165.154.201.52,47.245.87.207', 'https://init.lemonpay.cc/api/agentpay/query_order', 1);

-- 2025-05-16 接入第三方代付 188pay代付
INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `notify_ip`, `query_url`, `status`)
VALUES ('d215a782ef', 'db180159ccaf43a082faeda31fd903d5', 'https://api.188payindia.com/api/cash/placeCash', '188pay', '188支付', NULL, 0, 0, '15.206.99.184', 'https://api.188payindia.com/api/cash/queryCash', 1);

-- 2025-05-23 接入第三方代付 ospay代付
INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `notify_ip`, `query_url`, `status`)
VALUES ('403', '022cdde1a4b9357ad2e201faed901540', 'https://ospay689.com/api/pay/df', 'OSPAY', 'OSPAY支付', NULL, 0, 0, '34.117.168.59', 'https://ospay689.com/api/status/df', 1);

-- 2025-05-26 接入第三方代付 ospay UPI代付
INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `notify_ip`, `query_url`, `status`)
VALUES ('399', '2b1c8d8c27070b3bd822ef07e3567375', 'https://ospay689.com/api/pay/df', 'OSPAY_UPI', 'OSPAY UPI支付', NULL, 0, 0, '34.117.168.59', 'https://ospay689.com/api/status/df', 1);

-- 2025-5-24 TataPay代付开发
INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `notify_ip`, `query_url`, `status`, `mer_key2`, `mer_key3`, `mer_key4`) VALUES ('t100032', '1lk3762S942BzSpgR78n', 'https://api.tatapay.xyz/api/payOut', 'TataPay', 'TataPay支付', NULL, 0, 0, '13.200.39.182', 'https://api.tatapay.xyz/api/payOut/query', 1, '', '', NULL);

-- 2025-05-27 接入第三方代收 ospay
INSERT INTO `otherpay` (`merchant_id`, `key`, `name`, `pay_url`, `channel_code`, `query_url`, `status`, `notify_ip`)
VALUES ('399', '2b1c8d8c27070b3bd822ef07e3567375', 'ospay_upi', 'https://ospay689.com/api/pay', 1001, 'https://ospay689.com/api/status/ds', 1, '34.117.168.59,34.150.47.72');
-- 2025-05-27 接入第三方代收 ospay_upi
INSERT INTO `otherpay` (`merchant_id`, `key`, `name`, `pay_url`, `channel_code`, `query_url`, `status`, `notify_ip`)
VALUES ('403', '022cdde1a4b9357ad2e201faed901540', 'ospay', 'https://ospay689.com/api/pay', 1004, 'https://ospay689.com/api/status/ds', 1, '34.117.168.59,34.150.47.72');


-- 2025-5-27 sms_record remark字段增加长度至100
ALTER TABLE sms_record CHANGE COLUMN remark remark VARCHAR(100) COMMENT '备注';

-- 2025-05-30 接入第三方代收 789pay upi
INSERT INTO `otherpay` (`merchant_id`, `key`, `name`, `pay_url`, `channel_code`, `query_url`, `status`, `notify_ip`)
VALUES ('4', '924d90074921e7d6bf2091926b9bb504', '789pay_upi', 'https://api.789pay.top/api/pay', 1001, 'https://api.789pay.top/api/status/ds', 1, '34.92.69.39');

-- 2025-05-30 接入第三方代收 789pay
INSERT INTO `otherpay` (`merchant_id`, `key`, `name`, `pay_url`, `channel_code`, `query_url`, `status`, `notify_ip`)
VALUES ('5', 'eef739c01c494caef705b690bd20dad6', '789pay', 'https://api.789pay.top/api/pay', 1004, 'https://api.789pay.top/api/status/ds', 1, '34.92.69.39');

-- 2025-05-30 接入第三方代付 789pay UPI代付
INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `notify_ip`, `query_url`, `status`)
VALUES ('4', '924d90074921e7d6bf2091926b9bb504', 'https://api.789pay.top/api/pay/df', '789pay_upi', '789PAY支付 UPI支付', NULL, 0, 0, '34.92.69.39', 'https://api.789pay.top/api/status/df', 1);

-- 2025-05-30 接入第三方代付 789pay代付
INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `notify_ip`, `query_url`, `status`)
VALUES ('5', 'eef739c01c494caef705b690bd20dad6', 'https://api.789pay.top/api/pay/df', '789pay', '789PAY支付', NULL, 0, 0, '34.92.69.39', 'https://api.789pay.top/api/status/df', 1);


-- 2025-05-20 单码接多个订单
CREATE TABLE `bank_type_setting` (
  `id` int(11) NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `name` varchar(32) DEFAULT NULL COMMENT '银行名称',
  `type` int(10) DEFAULT '0' COMMENT '显示类型 0内部码商显示 1外部显示',
  `max_sec` int(11) DEFAULT '0' COMMENT '多长时间接单',
  `max_count` int(11) DEFAULT '0' COMMENT '最大接单次数',
  `status` tinyint(1) DEFAULT '1' COMMENT '0禁用1启用',
  `bank_id` int(11) DEFAULT '0' COMMENT '银行编号',
  PRIMARY KEY (`id`) USING BTREE
) COMMENT='银行卡系统设置表';

INSERT INTO `permissions` (`pid`, `name`, `path`, `type`, `status`, `level`, `admin_id`) VALUES (28, '接多单配置', '/setting/multi-payin', 0, 1, 2, 1);
-- 124是上面语句的数据id
INSERT INTO `permissions` (`pid`, `name`, `path`, `type`, `status`, `level`, `admin_id`) VALUES (124, '修改设置', '/partner/updateBankTypeSetting', 1, 1, 2, 1);
INSERT INTO `permissions` (`pid`, `name`, `path`, `type`, `status`, `level`, `admin_id`) VALUES (124, '添加设置', '/partner/addBankTypeSetting', 1, 1, 2, 1);
INSERT INTO `permissions` (`pid`, `name`, `path`, `type`, `status`, `level`, `admin_id`) VALUES (124, '设置启用禁用', '/partner/updateBankTypeStatusSetting', 1, 1, 2, 1);


-- 2025-5-26 接入第三方代收 TataPay代收
INSERT INTO otherpay (merchant_id, `key`, name, pay_url, channel_code, notify_ip, query_url)
VALUES ('t100033', '4q661c8622B15F45z4U7', 'TataPay', 'https://api.tatapay.xyz/api/payIn', 1004, '13.200.39.182', 'https://api.tatapay.xyz/api/payIn/query');

-- 2025-6-3 TataPay代付开发 收付一体 t100033
INSERT INTO `third_pay_df` (`mer_id`, `mer_key`, `pay_url`, `pay_name`, `pay_name_zh`, `channel_code`, `is_self`, `is_xiaoshu`, `notify_ip`, `query_url`, `status`, `mer_key2`, `mer_key3`, `mer_key4`)
VALUES ('t100033', '4q661c8622B15F45z4U7', 'https://api.tatapay.xyz/api/payOut', 'TataPay', 'TataPay支付t100033', NULL, 0, 0, '13.200.39.182', 'https://api.tatapay.xyz/api/payOut/query', 1, '', '', NULL);

-- 2025-6-27 payment表增加remarks字段
ALTER TABLE `payment` ADD COLUMN `remarks` longtext NULL COMMENT '保存换upi或登出的错误消息' AFTER `upi_list`;


-- refs-425 start ----------------------------------------
-- 2025-08-21 - hins

INSERT INTO bank_type (name, url, type, status, logo_url) VALUES ('EASYPAISA', NULL, 1, 1, NULL);

UPDATE `error_messages` SET 
`zh_message` = '手机号格式不正确，应以03开头共11位数字',
`zh_action` = '请输入正确的巴基斯坦手机号格式',
`en_message` = 'Phone number should start with 03 and be 11 digits long',
`en_action` = 'Please enter a valid Pakistan phone number'
WHERE `error_code` = 20002;

ALTER TABLE `payment`
  ALGORITHM=INPLACE,
  LOCK=NONE,
  ADD COLUMN `fingerprint_path` LONGTEXT
  CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL
  COMMENT '指纹文件存储位置';

ALTER TABLE `payment`
  ALGORITHM=INPLACE,
  LOCK=NONE,
  ADD COLUMN `account_entire` LONGTEXT
  CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL
  COMMENT '账户完整列表';

ALTER TABLE `payment`
  ALGORITHM=INPLACE,
  LOCK=NONE,
  ADD COLUMN `account_accno` VARCHAR(50)
  CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT NULL
  COMMENT '账户选中的accno';

ALTER TABLE `payment`
  ALGORITHM=INPLACE,
  LOCK=NONE,
  ADD COLUMN `account_iban` VARCHAR(50)
  CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT NULL
  COMMENT '账户选中的iban';

ALTER TABLE `payment_d`
  ALGORITHM=INPLACE,
  LOCK=NONE,
  MODIFY COLUMN `upi` VARCHAR(500)
  CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT NULL
  COMMENT 'UPI',
  MODIFY COLUMN `net_id` VARCHAR(64)
  CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT NULL
  COMMENT '网银登录ID',
  MODIFY COLUMN `net_pw` VARCHAR(64)
  CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT NULL
  COMMENT '网银登录密码',
  MODIFY COLUMN `time_update` DATETIME NULL DEFAULT CURRENT_TIMESTAMP
  ON UPDATE CURRENT_TIMESTAMP
  COMMENT '修改时间',
  ADD COLUMN `fingerprint_path` LONGTEXT
  CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT NULL
  COMMENT '指纹图路径',
  ADD COLUMN `account_entire` LONGTEXT
  CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT NULL
  COMMENT '账户完整列表',
  ADD COLUMN `account_selected` VARCHAR(100)
  CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT NULL
  COMMENT '账户选中项',
  ADD COLUMN `account_enable` TINYINT NULL DEFAULT 0
  COMMENT '账户启用状态',
  ADD COLUMN `account_accno` VARCHAR(50)
  CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT NULL
  COMMENT '账户选中的accno',
  ADD COLUMN `account_iban` VARCHAR(50)
  CHARACTER SET utf8 COLLATE utf8_unicode_ci NULL DEFAULT NULL
  COMMENT '账户选中的iban';

-- refs-425 end ----------------------------------------

-- 2026-04-01 -- Easypay SOAP 代收 (MA)
-- 商户后台名称：AbdulMoizE-Store
-- 映射关系：merchant_id=Account ID, key=Merchant Name, key2=API Key, key3=Store ID
INSERT INTO otherpay (merchant_id, `key`, key2, key3, pay_url, name, channel_code, query_url)
VALUES (
  '165338898',
  'AbdulMoizE-Store',
  '52cfb69eba523b459a2881038beda2cd',
  '1203411',
  'https://easypay.easypaisa.com.pk/easypay-service/PartnerBusinessService',
  'easypay',
  '1002',
  ''
);

-- 2026-05-01 EP 扫码自有代收通道
INSERT INTO `channel`
(`code`, `name`, `type`, `url`, `rate`, `rates`, `amount_min`, `amount_max`, `amount_fixed`, `fixed`, `status`, `decimal_callback_enabled`, `decimal_min`, `decimal_max`, `is_show_qr`)
VALUES (1010,'EP 扫码',1,'1',0.0001,'0.002,0.001',100.00,100000.00,NULL,0,1,0,0.01,0.99,0)
ON DUPLICATE KEY UPDATE
  `name` = VALUES(`name`),
  `type` = VALUES(`type`),
  `url` = VALUES(`url`),
  `rate` = VALUES(`rate`),
  `rates` = VALUES(`rates`),
  `amount_min` = VALUES(`amount_min`),
  `amount_max` = VALUES(`amount_max`),
  `amount_fixed` = VALUES(`amount_fixed`),
  `fixed` = VALUES(`fixed`),
  `status` = VALUES(`status`),
  `decimal_callback_enabled` = VALUES(`decimal_callback_enabled`),
  `decimal_min` = VALUES(`decimal_min`),
  `decimal_max` = VALUES(`decimal_max`),
  `is_show_qr` = VALUES(`is_show_qr`);
