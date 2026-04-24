ALTER TABLE `payment`
ADD COLUMN `pin` varchar(64) NULL COMMENT '银行PIN码' AFTER `phone`;

INSERT INTO `bank_type` (`id`, `name`, `url`, `type`, `status`, `logo_url`)
VALUES (70, 'INDUS', 'https://www.indusind.com/', 1, 1, 'https://laktoken.vip/indusind.png');
