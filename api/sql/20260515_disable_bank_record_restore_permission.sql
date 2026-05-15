-- 恢复接口已取消，废除流水由代收补单接口直接核销。
-- 如果历史环境已经写入 `/partner/restorebank_recoed` 权限，发布前应禁用，避免权限表残留误导运营。

UPDATE `permissions`
SET `status` = 0
WHERE `path` = '/partner/restorebank_recoed';
