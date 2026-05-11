-- Go worker balance-changed statement scan support.
-- 可重复执行；用于已跑过 Phase 0 的环境补齐官方余额快照与 balance_changed 审计枚举。

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

ALTER TABLE `worker_statement_scan_audit`
    MODIFY COLUMN `trigger_kind`
    ENUM('collect_pending','payout_unknown','balance_changed') NOT NULL;
