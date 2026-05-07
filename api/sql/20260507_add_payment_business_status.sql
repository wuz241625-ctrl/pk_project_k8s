ALTER TABLE `payment`
  ADD COLUMN `collection_status` TINYINT NOT NULL DEFAULT 0
  COMMENT '代收业务状态：0关闭 1开启'
  AFTER `wallet_status`,
  ADD COLUMN `payout_status` TINYINT NOT NULL DEFAULT 0
  COMMENT '代付业务状态：0关闭 1开启'
  AFTER `collection_status`;
