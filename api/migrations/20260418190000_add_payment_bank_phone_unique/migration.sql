UPDATE `payment` p
JOIN (
    SELECT `id`
    FROM (
        SELECT
            `id`,
            ROW_NUMBER() OVER (
                PARTITION BY `bank_type_id`, `phone`
                ORDER BY `status` DESC, `certified` DESC, `id` ASC
            ) AS `rn`
        FROM `payment`
        WHERE `phone` IS NOT NULL
          AND `phone` <> ''
    ) ranked
    WHERE ranked.`rn` > 1
) duplicates ON duplicates.`id` = p.`id`
SET p.`phone` = NULL
WHERE p.`phone` IS NOT NULL
  AND p.`phone` <> '';

SET @idx_exists := (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'payment'
      AND INDEX_NAME = 'uk_payment_bank_phone'
);

SET @ddl := IF(
    @idx_exists = 0,
    'ALTER TABLE `payment` ADD UNIQUE KEY `uk_payment_bank_phone` (`bank_type_id`, `phone`)',
    'SELECT ''uk_payment_bank_phone already exists'''
);

PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
