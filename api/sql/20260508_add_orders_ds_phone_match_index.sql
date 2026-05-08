-- EasyPaisa/JazzCash 代收按钱包、付款手机号、金额匹配订单的复合索引。
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
    'idx_orders_ds_payment_utr_amount_status_time',
    'ALTER TABLE `orders_ds` ADD INDEX `idx_orders_ds_payment_utr_amount_status_time` (`payment_id`, `utr`, `amount`, `status`, `time_create`), ALGORITHM=INPLACE, LOCK=NONE'
);

DROP PROCEDURE IF EXISTS add_index_if_missing;
