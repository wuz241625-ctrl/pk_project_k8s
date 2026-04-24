-- CreateTable
CREATE TABLE `admin` (
    `id` INTEGER NOT NULL AUTO_INCREMENT,
    `account` VARCHAR(64) NOT NULL,
    `hash_login` VARCHAR(128) NOT NULL,
    `name` VARCHAR(64) NOT NULL,
    `role` INTEGER NOT NULL,
    `ggkey` VARCHAR(64) NOT NULL,
    `status` INTEGER NOT NULL DEFAULT 1,
    `time_update` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),
    `time_create` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),

    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `balance_count_record` (
    `id` INTEGER NOT NULL AUTO_INCREMENT,
    `balance_p` DECIMAL(14, 4) NOT NULL,
    `balance_p_frozen` DECIMAL(14, 4) NOT NULL,
    `balance_p_deposit` DECIMAL(14, 4) NOT NULL,
    `balance_m` DECIMAL(14, 4) NOT NULL,
    `balance_m_frozen` DECIMAL(14, 4) NOT NULL,
    `created` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),

    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `balance_record` (
    `id` INTEGER NOT NULL AUTO_INCREMENT,
    `code` VARCHAR(64) NOT NULL,
    `change_before` DECIMAL(14, 4) NOT NULL,
    `amount` DECIMAL(14, 4) NOT NULL,
    `change_after` DECIMAL(14, 4) NOT NULL,
    `record_type` INTEGER NOT NULL DEFAULT 0,
    `admin_id` INTEGER NULL,
    `user_type` INTEGER NULL,
    `user_id` INTEGER NULL,
    `remark` VARCHAR(64) NULL,
    `time_create` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),

    INDEX `code`(`code`),
    INDEX `time_create`(`time_create`),
    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `bank_ifsc` (
    `id` INTEGER NOT NULL AUTO_INCREMENT,
    `BANK` VARCHAR(255) NULL,
    `IFSC` CHAR(11) NULL,
    `BRANCH` VARCHAR(255) NULL,
    `CENTRE` VARCHAR(255) NULL,
    `DISTRICT` VARCHAR(255) NULL,
    `STATE` VARCHAR(255) NULL,
    `ADDRESS` VARCHAR(255) NULL,
    `CONTACT` VARCHAR(255) NULL,
    `IMPS` VARCHAR(255) NULL,
    `RTGS` VARCHAR(255) NULL,
    `CITY` VARCHAR(255) NULL,
    `ISO3166` VARCHAR(255) NULL,
    `NEFT` VARCHAR(255) NULL,
    `MICR` INTEGER NULL,
    `UPI` VARCHAR(255) NULL,
    `SWIFT` VARCHAR(255) NULL,

    UNIQUE INDEX `ifsc`(`IFSC`),
    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `bank_record` (
    `id` INTEGER NOT NULL AUTO_INCREMENT,
    `admin_id` INTEGER NULL,
    `payment_id` INTEGER NOT NULL,
    `amount` DECIMAL(12, 2) NOT NULL,
    `content` VARCHAR(128) NULL,
    `trade_type` INTEGER NOT NULL DEFAULT 0,
    `utr` VARCHAR(32) NULL,
    `code` VARCHAR(32) NULL,
    `ifsc` VARCHAR(32) NULL,
    `order_code` VARCHAR(64) NULL,
    `callback` INTEGER NOT NULL DEFAULT 0,
    `time_create` DATETIME(0) NOT NULL DEFAULT CURRENT_TIMESTAMP(0),
    `ew_code` VARCHAR(64) NULL,
    `invalid` INTEGER NULL DEFAULT 0,
    `partner_id` INTEGER NOT NULL,

    INDEX `ind_partner_id_time_create`(`partner_id`, `time_create`),
    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `bank_type` (
    `id` INTEGER NOT NULL AUTO_INCREMENT,
    `name` VARCHAR(32) NULL,
    `url` VARCHAR(128) NULL,
    `type` INTEGER NULL DEFAULT 0,
    `logo_url` VARCHAR(191) NULL,

    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `channel` (
    `id` INTEGER NOT NULL AUTO_INCREMENT,
    `code` INTEGER NOT NULL,
    `name` VARCHAR(64) NOT NULL,
    `type` INTEGER NOT NULL,
    `url` VARCHAR(255) NOT NULL,
    `rate` DECIMAL(14, 4) NOT NULL,
    `rates` VARCHAR(64) NOT NULL,
    `amount_min` DECIMAL(12, 2) NULL,
    `amount_max` DECIMAL(12, 2) NULL,
    `amount_fixed` VARCHAR(255) NULL,
    `fixed` INTEGER NOT NULL,
    `status` INTEGER NOT NULL DEFAULT 1,
    `time_update` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),
    `time_create` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),

    UNIQUE INDEX `code`(`code`),
    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `daily` (
    `id` INTEGER NOT NULL AUTO_INCREMENT,
    `date` DATE NOT NULL,
    `balance_type` INTEGER NOT NULL,
    `record_type` INTEGER NOT NULL,
    `amount` DECIMAL(14, 4) NOT NULL,

    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `merchant` (
    `id` INTEGER NOT NULL AUTO_INCREMENT,
    `name` VARCHAR(64) NOT NULL,
    `cellphone` VARCHAR(64) NOT NULL,
    `hash_login` VARCHAR(128) NOT NULL,
    `gg_key` VARCHAR(64) NOT NULL,
    `balance` DECIMAL(14, 4) NOT NULL DEFAULT 0.0000,
    `balance_frozen` DECIMAL(14, 4) NOT NULL DEFAULT 0.0000,
    `fee_df` DECIMAL(14, 4) NOT NULL DEFAULT 0.0000,
    `rate_df` DECIMAL(14, 4) NOT NULL DEFAULT 0.0000,
    `mc_key` VARCHAR(64) NOT NULL,
    `return_url` BOOLEAN NOT NULL DEFAULT true,
    `status` INTEGER NOT NULL DEFAULT 1,
    `status_df` INTEGER NOT NULL DEFAULT 0,
    `pid` INTEGER NULL,
    `target_partner` VARCHAR(255) NULL,
    `ip` VARCHAR(255) NULL,
    `ip_df` VARCHAR(255) NULL,
    `time_update` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),
    `time_create` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),

    UNIQUE INDEX `name`(`name`),
    UNIQUE INDEX `cellphone`(`cellphone`),
    UNIQUE INDEX `time_create`(`time_create`),
    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `merchant_channel` (
    `id` INTEGER NOT NULL AUTO_INCREMENT,
    `merchant_id` INTEGER NOT NULL,
    `code` INTEGER NOT NULL,
    `rate` DECIMAL(14, 4) NOT NULL,
    `otherpay` INTEGER NULL,
    `is_force` INTEGER NULL DEFAULT 0,
    `target_channel` INTEGER NULL,
    `status` INTEGER NULL DEFAULT 1,

    INDEX `code`(`code`),
    INDEX `merchant_id`(`merchant_id`),
    INDEX `merchant_id_code_status`(`merchant_id`, `code`, `status`),
    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `merchant_tree` (
    `id` INTEGER NOT NULL AUTO_INCREMENT,
    `parent` INTEGER NOT NULL,
    `child` INTEGER NOT NULL,
    `distance` INTEGER NOT NULL,

    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `merchant_withdraw` (
    `id` INTEGER NOT NULL AUTO_INCREMENT,
    `code` VARCHAR(64) NOT NULL,
    `merchant_id` INTEGER NOT NULL,
    `address` VARCHAR(64) NOT NULL,
    `amount` DECIMAL(12, 2) NOT NULL,
    `status` INTEGER NOT NULL DEFAULT 0,
    `time_success` DATETIME(0) NULL,
    `time_updated` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),
    `time_create` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),
    `admin_id` INTEGER NULL,

    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `operate` (
    `id` INTEGER NOT NULL AUTO_INCREMENT,
    `type` INTEGER NULL,
    `admin_id` INTEGER NOT NULL,
    `ip` VARCHAR(64) NULL,
    `time_create` DATETIME(0) NOT NULL DEFAULT CURRENT_TIMESTAMP(0),

    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `orders_df` (
    `id` INTEGER NOT NULL AUTO_INCREMENT,
    `code` VARCHAR(64) NOT NULL,
    `amount` DECIMAL(12, 2) NOT NULL,
    `realpay` DECIMAL(14, 4) NOT NULL,
    `poundage` DECIMAL(14, 4) NOT NULL,
    `status` INTEGER NOT NULL DEFAULT 0,
    `payment_name` VARCHAR(64) NOT NULL,
    `payment_account` VARCHAR(64) NOT NULL,
    `payment_bank` VARCHAR(64) NOT NULL,
    `ifsc` VARCHAR(64) NOT NULL,
    `notice_api` VARCHAR(64) NULL,
    `notify` VARCHAR(128) NOT NULL,
    `remark` VARCHAR(128) NULL,
    `merchant_id` INTEGER NOT NULL,
    `merchant_code` VARCHAR(64) NOT NULL,
    `merchant_rate` DECIMAL(10, 4) NOT NULL,
    `earn_merchant` DECIMAL(10, 4) NOT NULL,
    `time_create` DATETIME(0) NOT NULL DEFAULT CURRENT_TIMESTAMP(0),
    `time_accept` DATETIME(0) NULL,
    `time_payed` DATETIME(0) NULL,
    `time_success` DATETIME(0) NULL,
    `time_updated` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),
    `partner_id` INTEGER NULL,
    `payment_id` INTEGER NULL,
    `earn_partner_self` DECIMAL(14, 4) NULL,
    `otherpay` VARCHAR(64) NULL,
    `earn_system` DECIMAL(10, 4) NULL,
    `payment_img` INTEGER NULL DEFAULT 0,
    `sys_remark` VARCHAR(255) NULL,

    UNIQUE INDEX `code`(`code`),
    INDEX `merchant_code`(`merchant_code`),
    INDEX `merchant_id_merchant_code`(`merchant_id`, `merchant_code`),
    INDEX `order_deposit_partner_id`(`partner_id`),
    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `orders_ds` (
    `id` INTEGER NOT NULL AUTO_INCREMENT,
    `code` VARCHAR(64) NOT NULL,
    `amount` DECIMAL(14, 2) NOT NULL,
    `realpay` DECIMAL(14, 4) NOT NULL,
    `poundage` DECIMAL(14, 4) NOT NULL,
    `channel_code` INTEGER NOT NULL,
    `status` INTEGER NOT NULL DEFAULT 0,
    `callback` VARCHAR(128) NOT NULL,
    `notice_api` VARCHAR(64) NULL,
    `notify` VARCHAR(256) NOT NULL,
    `player_ip` VARCHAR(64) NULL,
    `remark` VARCHAR(128) NULL,
    `pay_url` VARCHAR(128) NULL,
    `time_create` DATETIME(0) NOT NULL DEFAULT CURRENT_TIMESTAMP(0),
    `time_accept` DATETIME(0) NULL,
    `time_payed` DATETIME(0) NULL,
    `time_success` DATETIME(0) NULL,
    `merchant_id` INTEGER NOT NULL,
    `merchant_code` VARCHAR(128) NOT NULL,
    `merchant_rate` DECIMAL(10, 4) NOT NULL,
    `earn_merchant` DECIMAL(10, 4) NOT NULL,
    `partner_id` INTEGER NULL,
    `earn_partner_self` DECIMAL(14, 4) NULL,
    `earn_partner` DECIMAL(10, 4) NULL,
    `payment_id` INTEGER NULL,
    `utr` VARCHAR(64) NULL,
    `auth_code` VARCHAR(64) NOT NULL,
    `realname` VARCHAR(64) NULL,
    `player_provence` VARCHAR(64) NULL,
    `otherpay` VARCHAR(64) NULL,
    `earn_system` DECIMAL(10, 4) NULL DEFAULT 0.0000,
    `time_updated` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),
    `upi` VARCHAR(32) NULL,

    UNIQUE INDEX `code`(`code`),
    INDEX `auth_code`(`auth_code`),
    INDEX `merchant_code`(`merchant_code`),
    INDEX `order_withdraw_partner_id`(`partner_id`),
    INDEX `merchant_id_merchant_code`(`merchant_id`, `merchant_code`),
    INDEX `merchant_id_time_create`(`merchant_id`, `time_create`),
    INDEX `payment_id_status_time_create`(`payment_id`, `status`, `time_create`),
    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `otherpay` (
    `id` INTEGER NOT NULL AUTO_INCREMENT,
    `merchant_id` VARCHAR(255) NULL,
    `key` VARCHAR(255) NOT NULL,
    `key2` VARCHAR(255) NULL,
    `key3` VARCHAR(255) NULL,
    `name` VARCHAR(64) NOT NULL,
    `pay_url` VARCHAR(255) NOT NULL,
    `channel_code` INTEGER NULL,
    `notify_ip` VARCHAR(255) NULL,
    `query_url` VARCHAR(255) NULL,
    `forcible` INTEGER NOT NULL DEFAULT 0,
    `status` INTEGER NOT NULL DEFAULT 1,
    `updated` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),
    `created` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),

    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `partner` (
    `id` INTEGER NOT NULL AUTO_INCREMENT,
    `name` VARCHAR(64) NOT NULL,
    `cellphone` VARCHAR(32) NOT NULL,
    `email` VARCHAR(50) NULL,
    `hash_login` VARCHAR(128) NOT NULL,
    `hash_trade` VARCHAR(128) NOT NULL,
    `balance` DECIMAL(14, 4) NOT NULL DEFAULT 0.0000,
    `balance_frozen` DECIMAL(14, 4) NOT NULL DEFAULT 0.0000,
    `balance_deposit` DECIMAL(14, 4) NOT NULL DEFAULT 0.0000,
    `vip` INTEGER NOT NULL DEFAULT 1,
    `pid` INTEGER NULL,
    `status` INTEGER NOT NULL DEFAULT 1,
    `certified` INTEGER NOT NULL DEFAULT 0,
    `ip` INTEGER NULL DEFAULT 0,
    `time_update` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),
    `time_create` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),
    `type` INTEGER NULL DEFAULT 1,
    `invitation_code` VARCHAR(8) NULL,
    `ew_code` VARCHAR(64) NULL,
    `authentication_token` VARCHAR(64) NULL,

    UNIQUE INDEX `partner_cellphone_key`(`cellphone`),
    INDEX `cellphone`(`cellphone`),
    INDEX `name`(`name`),
    INDEX `pid`(`pid`),
    INDEX `time_create`(`time_create`),
    INDEX `authentication_token`(`authentication_token`),
    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `partner_recharge` (
    `id` INTEGER NOT NULL AUTO_INCREMENT,
    `code` VARCHAR(64) NOT NULL,
    `partner_id` INTEGER NOT NULL,
    `amount` DECIMAL(12, 2) NOT NULL,
    `admin_id` INTEGER NULL,
    `status` INTEGER NOT NULL DEFAULT 0,
    `time_success` DATETIME(0) NULL,
    `time_updated` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),
    `time_create` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),
    `sys_payment_id` INTEGER NULL,
    `ifsc` VARCHAR(64) NULL,
    `account` VARCHAR(64) NULL,
    `name` VARCHAR(64) NULL,
    `bank` VARCHAR(64) NULL,

    UNIQUE INDEX `code`(`code`),
    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `partner_tree` (
    `id` INTEGER NOT NULL AUTO_INCREMENT,
    `parent` INTEGER NOT NULL,
    `child` INTEGER NOT NULL,
    `distance` INTEGER NOT NULL,

    INDEX `partner_child_idx`(`child`),
    UNIQUE INDEX `partner_tree_parent_child_distance_key`(`parent`, `child`, `distance`),
    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `partner_withdraw` (
    `id` INTEGER NOT NULL AUTO_INCREMENT,
    `code` VARCHAR(64) NOT NULL,
    `partner_id` INTEGER NOT NULL,
    `amount` DECIMAL(12, 2) NOT NULL,
    `amount_order` DECIMAL(12, 2) NULL DEFAULT 0.00,
    `amount_success` DECIMAL(14, 0) NULL,
    `admin_id` INTEGER NULL,
    `status` INTEGER NOT NULL DEFAULT 0,
    `payment_codes` VARCHAR(255) NULL,
    `time_success` DATETIME(0) NULL,
    `time_updated` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),
    `time_create` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),
    `account` VARCHAR(64) NOT NULL,
    `name` VARCHAR(64) NOT NULL,
    `ifsc` VARCHAR(255) NOT NULL,
    `bank` VARCHAR(64) NOT NULL,

    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `payment` (
    `id` INTEGER NOT NULL AUTO_INCREMENT,
    `bank_type` VARCHAR(32) NOT NULL,
    `account_type` INTEGER NULL,
    `upi` VARCHAR(32) NULL,
    `ifsc` VARCHAR(32) NULL,
    `account` VARCHAR(32) NULL,
    `name` VARCHAR(32) NULL,
    `net_id` VARCHAR(32) NULL,
    `net_pw` VARCHAR(32) NULL,
    `net_trade_pw` VARCHAR(32) NULL,
    `phone` VARCHAR(16) NULL,
    `gmail` VARCHAR(64) NULL,
    `gmail_pw` VARCHAR(32) NULL,
    `sys_balance` DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    `balance` DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    `partner_id` INTEGER NOT NULL,
    `certified` INTEGER NOT NULL DEFAULT 0,
    `status` INTEGER NOT NULL DEFAULT 0,
    `time_create` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),
    `amount_top` DECIMAL(12, 2) NULL,
    `bank_type_id` INTEGER NOT NULL DEFAULT 0,

    INDEX `accout`(`account`),
    INDEX `bank_type`(`bank_type`),
    INDEX `gmail`(`gmail`),
    INDEX `partner_id`(`partner_id`),
    INDEX `payment_bank_type_id`(`bank_type_id`),
    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `payment_d` (
    `id` INTEGER NOT NULL AUTO_INCREMENT,
    `bank_type` VARCHAR(32) NOT NULL,
    `account_type` INTEGER NULL,
    `upi` VARCHAR(32) NULL,
    `ifsc` VARCHAR(32) NULL,
    `account` VARCHAR(32) NULL,
    `name` VARCHAR(64) NULL,
    `net_id` VARCHAR(32) NULL,
    `net_pw` VARCHAR(32) NULL,
    `net_trade_pw` VARCHAR(32) NULL,
    `phone` VARCHAR(16) NULL,
    `gmail` VARCHAR(64) NULL,
    `gmail_pw` VARCHAR(32) NULL,
    `sys_balance` DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    `balance` DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    `partner_id` INTEGER NOT NULL,
    `certified` INTEGER NOT NULL DEFAULT 0,
    `status` INTEGER NOT NULL DEFAULT 0,
    `time_create` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),
    `amount_top` DECIMAL(12, 2) NULL,

    INDEX `account`(`account`),
    INDEX `partner_id`(`partner_id`),
    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `permissions` (
    `id` INTEGER NOT NULL AUTO_INCREMENT,
    `pid` INTEGER NOT NULL,
    `name` VARCHAR(64) NOT NULL,
    `path` VARCHAR(255) NOT NULL,
    `type` INTEGER NOT NULL DEFAULT 1,
    `status` INTEGER NOT NULL DEFAULT 1,

    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `phonepe` (
    `id` INTEGER NOT NULL AUTO_INCREMENT,
    `pw` VARCHAR(64) NOT NULL DEFAULT '123456',
    `payment_id` INTEGER NULL,
    `status` INTEGER NOT NULL DEFAULT 0,
    `occupied` INTEGER NOT NULL DEFAULT 0,
    `time_create` DATETIME(0) NOT NULL DEFAULT CURRENT_TIMESTAMP(0),

    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `roles` (
    `id` INTEGER NOT NULL AUTO_INCREMENT,
    `key_name` VARCHAR(64) NOT NULL,
    `name` VARCHAR(64) NOT NULL,
    `permissions` VARCHAR(255) NOT NULL,
    `description` VARCHAR(255) NOT NULL,
    `time_update` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),
    `time_create` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),

    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `sys_info` (
    `id` INTEGER NOT NULL,
    `sys_ip_w` LONGTEXT NULL,
    `api_ip_b` LONGTEXT NULL,
    `bulletin` VARCHAR(255) NULL,
    `telegram` VARCHAR(255) NULL,
    `rate_df` DECIMAL(14, 4) NULL,

    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `sys_payment` (
    `id` INTEGER NOT NULL AUTO_INCREMENT,
    `account` VARCHAR(64) NOT NULL,
    `name` VARCHAR(64) NOT NULL,
    `type` VARCHAR(64) NOT NULL DEFAULT '1',
    `admin_id` INTEGER NOT NULL,
    `status` INTEGER NOT NULL DEFAULT 1,
    `time_update` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),
    `time_create` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),
    `ifsc` VARCHAR(32) NULL,
    `bank` VARCHAR(64) NULL,

    UNIQUE INDEX `account`(`account`),
    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `sys_record` (
    `id` INTEGER NOT NULL AUTO_INCREMENT,
    `code` VARCHAR(64) NOT NULL,
    `amount` DECIMAL(14, 4) NOT NULL,
    `record_type` INTEGER NOT NULL DEFAULT 0,
    `admin_id` INTEGER NULL,
    `remark` VARCHAR(64) NULL,
    `time_create` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),
    `name` VARCHAR(64) NULL,
    `account` VARCHAR(64) NULL,
    `type` VARCHAR(64) NULL,

    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `transfer` (
    `id` INTEGER NOT NULL AUTO_INCREMENT,
    `code` VARCHAR(64) NOT NULL,
    `partner_id` INTEGER NOT NULL,
    `to_partner_id` INTEGER NOT NULL,
    `amount` DECIMAL(12, 2) NOT NULL,
    `admin_id` INTEGER NULL,
    `status` INTEGER NOT NULL DEFAULT 1,
    `time_success` DATETIME(0) NULL,
    `time_updated` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),
    `time_create` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),
    `type` INTEGER NOT NULL DEFAULT 1,
    `remark` VARCHAR(255) NULL,

    UNIQUE INDEX `code`(`code`),
    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `vip` (
    `vip` INTEGER NOT NULL,
    `conditions` DECIMAL(12, 2) NOT NULL,
    `ds_min` DECIMAL(12, 2) NOT NULL,
    `ds_max` DECIMAL(12, 2) NOT NULL,
    `df_min` DECIMAL(12, 2) NOT NULL,
    `df_max` DECIMAL(12, 2) NOT NULL,
    `top_card` INTEGER NOT NULL DEFAULT 1,
    `deposit_ratio` TINYINT NOT NULL DEFAULT 20,

    PRIMARY KEY (`vip`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `text_materials` (
    `id` INTEGER NOT NULL AUTO_INCREMENT,
    `genre` VARCHAR(191) NOT NULL,
    `title` VARCHAR(191) NOT NULL,
    `content` TEXT NOT NULL,
    `updated_at` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),
    `created_at` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),

    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `lakshmi_api_settings` (
    `id` INTEGER NOT NULL AUTO_INCREMENT,
    `genre` VARCHAR(191) NOT NULL,
    `name` VARCHAR(191) NOT NULL,
    `key` VARCHAR(191) NOT NULL,
    `value` VARCHAR(191) NOT NULL,
    `updated_at` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),
    `created_at` DATETIME(0) NULL DEFAULT CURRENT_TIMESTAMP(0),

    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
