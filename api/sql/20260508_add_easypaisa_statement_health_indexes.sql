-- EasyPaisa 账单采集 + 健康余额统一调度索引
-- 可重复执行；已有索引会跳过。

DROP PROCEDURE IF EXISTS add_index_if_missing;

DELIMITER //
CREATE PROCEDURE add_index_if_missing(
    IN p_table_name VARCHAR(64),
    IN p_index_name VARCHAR(64),
    IN p_ddl TEXT
)
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.STATISTICS
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

CALL add_index_if_missing(
    'orders_ds',
    'idx_orders_ds_status_time_payment',
    'ALTER TABLE `orders_ds` ADD INDEX `idx_orders_ds_status_time_payment` (`status`, `time_create`, `payment_id`), ALGORITHM=INPLACE, LOCK=NONE'
);

CALL add_index_if_missing(
    'orders_df',
    'idx_orders_df_status_accept_payment',
    'ALTER TABLE `orders_df` ADD INDEX `idx_orders_df_status_accept_payment` (`status`, `time_accept`, `payment_id`), ALGORITHM=INPLACE, LOCK=NONE'
);

CALL add_index_if_missing(
    'payment',
    'idx_payment_wallet_bank_type_id',
    'ALTER TABLE `payment` ADD INDEX `idx_payment_wallet_bank_type_id` (`wallet_status`, `bank_type_id`, `id`), ALGORITHM=INPLACE, LOCK=NONE'
);

CALL add_index_if_missing(
    'payment',
    'idx_payment_wallet_bank_type',
    'ALTER TABLE `payment` ADD INDEX `idx_payment_wallet_bank_type` (`wallet_status`, `bank_type`, `id`), ALGORITHM=INPLACE, LOCK=NONE'
);

DROP PROCEDURE IF EXISTS add_index_if_missing;
