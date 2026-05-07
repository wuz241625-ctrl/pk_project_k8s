ALTER TABLE `payment`
  ADD COLUMN `wallet_status` TINYINT NOT NULL DEFAULT 0
  COMMENT '钱包状态：0不可用 1可用'
  AFTER `account_iban`;
