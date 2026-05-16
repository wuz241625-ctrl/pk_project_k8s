-- Go worker 代付尝试审计表。
-- 可重复执行；用于已有 D7pay 库升级到 append-only transfer attempt 方案。

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
        FROM information_schema.COLUMNS
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

CALL add_column_if_missing(
    'worker_transfer_intent',
    'latest_attempt_id',
    'ALTER TABLE `worker_transfer_intent` ADD COLUMN `latest_attempt_id` BIGINT UNSIGNED NULL AFTER `request_id`, ALGORITHM=INPLACE, LOCK=NONE'
);

CALL add_column_if_missing(
    'worker_transfer_intent',
    'success_attempt_id',
    'ALTER TABLE `worker_transfer_intent` ADD COLUMN `success_attempt_id` BIGINT UNSIGNED NULL AFTER `latest_attempt_id`, ALGORITHM=INPLACE, LOCK=NONE'
);

CALL add_index_if_missing(
    'worker_transfer_intent',
    'idx_worker_transfer_intent_latest_attempt',
    'ALTER TABLE `worker_transfer_intent` ADD KEY `idx_worker_transfer_intent_latest_attempt` (`latest_attempt_id`), ALGORITHM=INPLACE, LOCK=NONE'
);

CALL add_index_if_missing(
    'worker_transfer_intent',
    'idx_worker_transfer_intent_success_attempt',
    'ALTER TABLE `worker_transfer_intent` ADD KEY `idx_worker_transfer_intent_success_attempt` (`success_attempt_id`), ALGORITHM=INPLACE, LOCK=NONE'
);

CREATE TABLE IF NOT EXISTS `worker_transfer_attempt` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `order_code` VARCHAR(64) NOT NULL,
    `attempt_no` INT UNSIGNED NOT NULL,
    `request_id` VARCHAR(96) NOT NULL,
    `payment_id` BIGINT NOT NULL,
    `partner_id` BIGINT NOT NULL,
    `channel` VARCHAR(32) NOT NULL,
    `amount` DECIMAL(14, 4) NOT NULL,
    `action` VARCHAR(64) NOT NULL,
    `request_payload_raw` LONGTEXT NULL COMMENT '官方请求原文，用于监控和人工复盘，不做脱敏或字段截断',
    `response_payload_raw` LONGTEXT NULL COMMENT '官方响应原文，用于监控和人工复盘，不做脱敏或字段截断',
    `official_code` VARCHAR(32) NULL,
    `official_message` VARCHAR(512) NULL,
    `official_transaction_id` VARCHAR(128) NULL,
    `result` ENUM('failed_retryable','failed_final','unknown_manual','success_pending_settlement','success') NOT NULL,
    `error_message` VARCHAR(512) NULL,
    `submitted_at` DATETIME NOT NULL,
    `finished_at` DATETIME NULL,
    `settled_at` DATETIME NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_worker_transfer_attempt_request` (`request_id`),
    UNIQUE KEY `uk_worker_transfer_attempt_order_no` (`order_code`, `attempt_no`),
    KEY `idx_worker_transfer_attempt_order` (`order_code`, `created_at`),
    KEY `idx_worker_transfer_attempt_payment` (`payment_id`, `channel`, `created_at`),
    KEY `idx_worker_transfer_attempt_result` (`result`, `created_at`),
    KEY `idx_worker_transfer_attempt_official_txn` (`official_transaction_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

DROP PROCEDURE IF EXISTS add_column_if_missing;
DROP PROCEDURE IF EXISTS add_index_if_missing;
