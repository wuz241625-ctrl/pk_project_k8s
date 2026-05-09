-- D7pay 资金一致性约束。
-- 执行前会检查重复数据；发现重复时跳过对应唯一约束，避免直接中断线上服务。
-- 业务存储仍保持 UTC，本文件不修改时区配置。

DROP PROCEDURE IF EXISTS add_column_if_missing;
DROP PROCEDURE IF EXISTS add_index_if_missing;

DELIMITER //
CREATE PROCEDURE add_column_if_missing(
    IN p_table_name VARCHAR(64),
    IN p_column_name VARCHAR(64),
    IN p_ddl TEXT
)
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = p_table_name
          AND COLUMN_NAME = p_column_name
        LIMIT 1
    ) THEN
        SET @ddl = p_ddl;
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END//

CREATE PROCEDURE add_index_if_missing(
    IN p_table_name VARCHAR(64),
    IN p_index_name VARCHAR(64),
    IN p_ddl TEXT
)
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = p_table_name
          AND INDEX_NAME = p_index_name
        LIMIT 1
    ) THEN
        SET @ddl = p_ddl;
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END//
DELIMITER ;

CREATE TABLE IF NOT EXISTS `balance_record_idempotency` (
    `idempotency_key` CHAR(64) NOT NULL,
    `code` VARCHAR(64) NOT NULL,
    `user_type` INT NULL,
    `user_id` INT NULL,
    `amount` DECIMAL(14,4) NULL,
    `record_type` INT NULL,
    `time_create` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`idempotency_key`),
    KEY `idx_balance_record_idempotency_code` (`code`),
    KEY `idx_balance_record_idempotency_time` (`time_create`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET @orders_df_merchant_duplicate_count := (
    SELECT COUNT(*)
    FROM (
        SELECT `merchant_id`, `merchant_code`
        FROM `orders_df`
        GROUP BY `merchant_id`, `merchant_code`
        HAVING COUNT(*) > 1
    ) duplicate_orders_df_merchant_code
);

SET @orders_df_old_idx_exists := (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'orders_df'
      AND INDEX_NAME = 'merchant_id_merchant_code'
);

SET @drop_orders_df_old_idx := IF(
    @orders_df_merchant_duplicate_count = 0 AND @orders_df_old_idx_exists > 0,
    'ALTER TABLE `orders_df` DROP INDEX `merchant_id_merchant_code`, ALGORITHM=INPLACE, LOCK=NONE',
    'SELECT ''orders_df merchant_id_merchant_code old index drop skipped'''
);
PREPARE stmt FROM @drop_orders_df_old_idx;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @add_orders_df_unique_idx := IF(
    @orders_df_merchant_duplicate_count = 0,
    'ALTER TABLE `orders_df` ADD UNIQUE KEY `uk_orders_df_merchant_code` (`merchant_id`, `merchant_code`), ALGORITHM=INPLACE, LOCK=NONE',
    'SELECT ''orders_df merchant_id + merchant_code unique index add skipped because duplicates exist'''
);
CALL add_index_if_missing('orders_df', 'uk_orders_df_merchant_code', @add_orders_df_unique_idx);

CALL add_column_if_missing(
    'orders_ds',
    'orders_ds_trans_id_unique',
    'ALTER TABLE `orders_ds` ADD COLUMN `orders_ds_trans_id_unique` VARCHAR(128) GENERATED ALWAYS AS (NULLIF(`trans_id`, '''')) STORED INVISIBLE'
);

SET @orders_ds_trans_duplicate_count := (
    SELECT COUNT(*)
    FROM (
        SELECT `orders_ds_trans_id_unique`
        FROM `orders_ds`
        WHERE `orders_ds_trans_id_unique` IS NOT NULL
        GROUP BY `orders_ds_trans_id_unique`
        HAVING COUNT(*) > 1
    ) duplicate_orders_ds_trans_id
);

SET @add_orders_ds_trans_unique := IF(
    @orders_ds_trans_duplicate_count = 0,
    'ALTER TABLE `orders_ds` ADD UNIQUE KEY `uk_orders_ds_trans_id_unique` (`orders_ds_trans_id_unique`), ALGORITHM=INPLACE, LOCK=NONE',
    'SELECT ''orders_ds trans_id unique index add skipped because duplicates exist'''
);
CALL add_index_if_missing('orders_ds', 'uk_orders_ds_trans_id_unique', @add_orders_ds_trans_unique);

CALL add_column_if_missing(
    'bank_record',
    'bank_record_trans_id_unique',
    'ALTER TABLE `bank_record` ADD COLUMN `bank_record_trans_id_unique` VARCHAR(128) GENERATED ALWAYS AS (NULLIF(`trans_id`, '''')) STORED INVISIBLE'
);

SET @bank_record_trans_duplicate_count := (
    SELECT COUNT(*)
    FROM (
        SELECT `payment_id`, `trade_type`, `bank_record_trans_id_unique`
        FROM `bank_record`
        WHERE `bank_record_trans_id_unique` IS NOT NULL
        GROUP BY `payment_id`, `trade_type`, `bank_record_trans_id_unique`
        HAVING COUNT(*) > 1
    ) duplicate_bank_record_trans_id
);

SET @add_bank_record_trans_unique := IF(
    @bank_record_trans_duplicate_count = 0,
    'ALTER TABLE `bank_record` ADD UNIQUE KEY `uk_bank_record_payment_trade_trans` (`payment_id`, `trade_type`, `bank_record_trans_id_unique`), ALGORITHM=INPLACE, LOCK=NONE',
    'SELECT ''bank_record trans_id unique index add skipped because duplicates exist'''
);
CALL add_index_if_missing('bank_record', 'uk_bank_record_payment_trade_trans', @add_bank_record_trans_unique);

DROP PROCEDURE IF EXISTS add_column_if_missing;
DROP PROCEDURE IF EXISTS add_index_if_missing;
