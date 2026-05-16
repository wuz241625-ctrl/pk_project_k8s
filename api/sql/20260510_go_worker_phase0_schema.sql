-- Go worker + asynq Phase 0 schema.
-- 可重复执行；只新增兼容字段/表，不删除旧列，不改旧 worker 运行入口。

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
    'balance_record',
    'idempotency_key',
    'ALTER TABLE `balance_record` ADD COLUMN `idempotency_key` VARCHAR(128) NULL COMMENT ''Go worker 幂等键，旧 Python 可为空'' AFTER `merchant_code`, ALGORITHM=INPLACE, LOCK=NONE'
);

CALL add_index_if_missing(
    'balance_record',
    'uk_balance_record_idempotency_key',
    'ALTER TABLE `balance_record` ADD UNIQUE KEY `uk_balance_record_idempotency_key` (`idempotency_key`), ALGORITHM=INPLACE, LOCK=NONE'
);

CREATE TABLE IF NOT EXISTS `worker_task_outbox` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `event_type` VARCHAR(64) NOT NULL,
    `aggregate_type` VARCHAR(32) NOT NULL,
    `aggregate_id` VARCHAR(64) NOT NULL,
    `task_type` VARCHAR(64) NOT NULL,
    `queue` VARCHAR(32) NOT NULL DEFAULT 'default',
    `payload` JSON NOT NULL,
    `unique_key` VARCHAR(160) NOT NULL,
    `process_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `status` ENUM('pending','locked','enqueued','failed','dead') NOT NULL DEFAULT 'pending',
    `retry_count` INT UNSIGNED NOT NULL DEFAULT 0,
    `next_retry_at` DATETIME NULL,
    `last_error` VARCHAR(512) NULL,
    `locked_by` VARCHAR(64) NULL,
    `locked_at` DATETIME NULL,
    `asynq_task_id` VARCHAR(190) NULL,
    `enqueued_at` DATETIME NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_worker_task_outbox_unique_key` (`unique_key`),
    KEY `idx_worker_task_outbox_due` (`status`, `process_at`, `id`),
    KEY `idx_worker_task_outbox_retry` (`status`, `next_retry_at`, `id`),
    KEY `idx_worker_task_outbox_aggregate` (`aggregate_type`, `aggregate_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `worker_task_outbox_ref` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `outbox_id` BIGINT UNSIGNED NOT NULL,
    `trace_id` VARCHAR(128) NOT NULL,
    `order_code` VARCHAR(64) NOT NULL,
    `trigger_kind` ENUM('collect_pending','payout_unknown') NOT NULL,
    `payment_id` BIGINT NOT NULL,
    `channel` VARCHAR(32) NOT NULL,
    `time_bucket` VARCHAR(32) NOT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_outbox_ref_order` (`outbox_id`, `order_code`, `trigger_kind`),
    KEY `idx_outbox_ref_order` (`order_code`, `created_at`),
    KEY `idx_outbox_ref_trace` (`trace_id`),
    KEY `idx_outbox_ref_payment` (`payment_id`, `channel`, `time_bucket`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `worker_statement_scan_audit` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `mode` ENUM('shadow','active') NOT NULL,
    `outbox_id` BIGINT UNSIGNED NULL,
    `asynq_task_id` VARCHAR(190) NULL,
    `trigger_order_code` VARCHAR(64) NULL,
    `order_code` VARCHAR(64) NULL,
    `trigger_kind` ENUM('collect_pending','payout_unknown','balance_changed') NOT NULL,
    `payment_id` BIGINT NOT NULL,
    `channel` VARCHAR(32) NOT NULL,
    `time_bucket` VARCHAR(32) NOT NULL,
    `python_match_result` JSON NULL,
    `go_match_result` JSON NULL,
    `amount_diff` DECIMAL(14, 4) NULL,
    `result` ENUM('matched','not_matched','diff','settled','skipped','error') NOT NULL,
    `reason` VARCHAR(512) NULL,
    `statement_trans_id` VARCHAR(128) NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_worker_statement_scan_audit_order` (`trigger_order_code`, `created_at`),
    KEY `idx_worker_statement_scan_audit_candidate_order` (`order_code`, `created_at`),
    KEY `idx_worker_statement_scan_audit_payment` (`payment_id`, `channel`, `time_bucket`),
    KEY `idx_worker_statement_scan_audit_outbox` (`outbox_id`, `created_at`),
    KEY `idx_worker_statement_scan_audit_result` (`mode`, `result`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `worker_payment_balance_snapshot` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `payment_id` BIGINT NOT NULL,
    `channel` VARCHAR(32) NOT NULL,
    `official_balance` DECIMAL(14, 4) NOT NULL,
    `last_checked_at` DATETIME NOT NULL,
    `last_changed_at` DATETIME NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_worker_payment_balance_snapshot_payment` (`payment_id`, `channel`),
    KEY `idx_worker_payment_balance_snapshot_changed` (`channel`, `last_changed_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `worker_transfer_intent` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `order_code` VARCHAR(64) NOT NULL,
    `channel` VARCHAR(32) NOT NULL,
    `payment_id` BIGINT NULL,
    `amount` DECIMAL(14, 4) NOT NULL,
    `request_id` VARCHAR(96) NOT NULL,
    `latest_attempt_id` BIGINT UNSIGNED NULL,
    `success_attempt_id` BIGINT UNSIGNED NULL,
    `status` ENUM('created','submitted','success_pending_settlement','success','failed_retryable','failed_final','unknown_manual','settlement_failed_manual','cancelled') NOT NULL DEFAULT 'created',
    `official_transaction_id` VARCHAR(128) NULL,
    `official_status` VARCHAR(64) NULL,
    `last_error` VARCHAR(512) NULL,
    `request_payload_raw` LONGTEXT NULL COMMENT '官方请求原文，用于监控和人工复盘，不做脱敏或字段截断',
    `response_payload_raw` LONGTEXT NULL COMMENT '官方响应原文，用于监控和人工复盘，不做脱敏或字段截断',
    `request_payload_json` JSON NULL COMMENT '可解析时保存的官方请求JSON副本，不能替代raw原文',
    `response_payload_json` JSON NULL COMMENT '可解析时保存的官方响应JSON副本，不能替代raw原文',
    `submitted_at` DATETIME NULL,
    `unknown_at` DATETIME NULL,
    `settled_at` DATETIME NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_worker_transfer_intent_order` (`order_code`),
    UNIQUE KEY `uk_worker_transfer_intent_request` (`request_id`),
    KEY `idx_worker_transfer_intent_status` (`status`, `updated_at`),
    KEY `idx_worker_transfer_intent_latest_attempt` (`latest_attempt_id`),
    KEY `idx_worker_transfer_intent_success_attempt` (`success_attempt_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

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
