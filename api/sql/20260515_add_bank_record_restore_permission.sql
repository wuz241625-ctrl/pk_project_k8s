-- 银行流水恢复权限。
-- 新增 `/partner/restorebank_recoed` 后必须写入权限表，否则 BaseHandler 在找不到路径时会默认放行。

INSERT INTO `permissions` (`pid`, `name`, `path`, `type`, `status`, `level`, `admin_id`)
SELECT 24, '恢复', '/partner/restorebank_recoed', 1, 1, 2, 1
FROM DUAL
WHERE NOT EXISTS (
    SELECT 1
    FROM `permissions`
    WHERE `path` = '/partner/restorebank_recoed'
    LIMIT 1
);

