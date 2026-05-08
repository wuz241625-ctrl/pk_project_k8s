SET @duplicate_count := (
    SELECT COUNT(*)
    FROM (
        SELECT `merchant_id`, `merchant_code`
        FROM `orders_ds`
        GROUP BY `merchant_id`, `merchant_code`
        HAVING COUNT(*) > 1
    ) duplicate_orders_ds_merchant_code
);

SET @old_idx_exists := (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'orders_ds'
      AND INDEX_NAME = 'merchant_id_merchant_code'
);

SET @unique_idx_exists := (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'orders_ds'
      AND INDEX_NAME = 'uk_orders_ds_merchant_code'
);

SET @drop_old_idx := IF(
    @duplicate_count = 0 AND @old_idx_exists > 0,
    'ALTER TABLE `orders_ds` DROP INDEX `merchant_id_merchant_code`',
    'SELECT ''orders_ds merchant_id_merchant_code old index drop skipped'''
);

PREPARE stmt FROM @drop_old_idx;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @add_unique_idx := IF(
    @duplicate_count = 0 AND @unique_idx_exists = 0,
    'ALTER TABLE `orders_ds` ADD UNIQUE KEY `uk_orders_ds_merchant_code` (`merchant_id`, `merchant_code`)',
    'SELECT ''orders_ds merchant_id + merchant_code unique index add skipped'''
);

PREPARE stmt FROM @add_unique_idx;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
