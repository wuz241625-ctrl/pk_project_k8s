# 演示数据整理脚本构建与执行

## 本地验证

```bash
cd /Users/tear/pk_project_k8s
python3 -m unittest ops/demo_data/test_prepare_demo_data.py -v
python3 -m py_compile ops/demo_data/prepare_demo_data.py
```

## 线上 dry-run

脚本现在必须从旧库快照抽真实业务样本。当前测试环境使用的源库是：

```text
pakistan_backup_inspect_20260425
```

如果源库不存在，先把执行前备份恢复到隔离库，再执行脚本。不要直接从已经整理过的 `pakistan` 再抽样，否则会把演示数据再次当作旧数据使用。

```bash
export KUBECONFIG=/etc/kubernetes/admin.conf
ADMIN_POD=$(kubectl get pods -n pk -l app=admin -o jsonpath='{.items[0].metadata.name}')
kubectl exec -i -n pk "$ADMIN_POD" -- sh -lc 'cat > /tmp/prepare_demo_data.py' < ops/demo_data/prepare_demo_data.py
kubectl exec -n pk "$ADMIN_POD" -- python /tmp/prepare_demo_data.py \
  --source-database=pakistan_backup_inspect_20260425
```

如果为释放 MySQL 元数据锁临时把 admin 缩容到 0，可以用 admin 镜像启动一次性 runner：

```bash
export KUBECONFIG=/etc/kubernetes/admin.conf
kubectl run demo-data-runner -n pk \
  --image=<admin-image> \
  --restart=Never \
  --env=RUN_ENV=PROD \
  --env=REDIS_HOST=redis \
  --env=REDIS_PORT=6379 \
  --env=MYSQL_HOST=mysql \
  --command -- sh -lc 'sleep 3600'
kubectl wait -n pk --for=condition=Ready pod/demo-data-runner --timeout=120s
kubectl exec -i -n pk demo-data-runner -- sh -lc 'cat > /tmp/prepare_demo_data.py' < ops/demo_data/prepare_demo_data.py
kubectl exec -n pk demo-data-runner -- python /tmp/prepare_demo_data.py \
  --source-database=pakistan_backup_inspect_20260425
```

## 线上执行

执行前必须备份：

```bash
mkdir -p /opt/cicd/k8s/backups
KUBECONFIG=/etc/kubernetes/admin.conf kubectl exec -n pk mysql-0 -- \
  sh -lc 'mysqldump -uroot -pPass_1234 --single-transaction --quick pakistan | gzip -c' \
  > /opt/cicd/k8s/backups/pakistan-demo-before-$(date +%Y%m%d%H%M%S).sql.gz
```

执行整理：

```bash
export KUBECONFIG=/etc/kubernetes/admin.conf
ADMIN_POD=$(kubectl get pods -n pk -l app=admin -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n pk "$ADMIN_POD" -- python /tmp/prepare_demo_data.py \
  --source-database=pakistan_backup_inspect_20260425 \
  --apply \
  --i-understand-this-rewrites-test-data
```

整理后清 Redis 运行态：

```bash
REDIS_POD=$(kubectl get pods -n pk -l app=redis -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n pk "$REDIS_POD" -- redis-cli --scan --pattern 'payment_*' | \
  xargs -r -I{} kubectl exec -n pk "$REDIS_POD" -- redis-cli DEL "{}"
kubectl exec -n pk "$REDIS_POD" -- redis-cli --scan --pattern 'easypaisa_runtime:*' | \
  xargs -r -I{} kubectl exec -n pk "$REDIS_POD" -- redis-cli DEL "{}"
kubectl exec -n pk "$REDIS_POD" -- redis-cli DEL target_payment_key cache_info_sys_info_1
```

重启服务并确认生产模式：

```bash
kubectl rollout restart deployment/admin-deploy deployment/api-deploy deployment/merchant-deploy -n pk
kubectl rollout status deployment/admin-deploy -n pk --timeout=180s
kubectl rollout status deployment/api-deploy -n pk --timeout=180s
kubectl rollout status deployment/merchant-deploy -n pk --timeout=180s
for d in admin-deploy api-deploy merchant-deploy; do
  kubectl get deploy -n pk "$d" -o jsonpath='{range .spec.template.spec.containers[0].env[*]}{.name}={.value}{"\n"}{end}' | grep RUN_ENV
done
```

## 验收

```bash
kubectl exec -i -n pk mysql-0 -- mysql -uroot -pPass_1234 -D pakistan -N -B <<'SQL'
SELECT 'admin', COUNT(*) FROM admin;
SELECT 'roles', COUNT(*) FROM roles;
SELECT 'merchant', COUNT(*) FROM merchant;
SELECT 'partner', COUNT(*) FROM partner;
SELECT 'payment', COUNT(*) FROM payment;
SELECT 'payment_active_count', COUNT(*) FROM payment WHERE status=1 OR manual_status=0;
SELECT 'payment_d', COUNT(*) FROM payment_d;
SELECT 'orders_ds', COUNT(*) FROM orders_ds;
SELECT 'orders_df', COUNT(*) FROM orders_df;
SELECT 'balance_record', COUNT(*) FROM balance_record;
SELECT 'merchant_target_payment_nonempty', COUNT(*) FROM merchant WHERE target_payment IS NOT NULL AND target_payment != '';
SELECT 'merchant_negative_balance', COUNT(*) FROM merchant WHERE balance < 0 OR balance_frozen < 0;
SELECT 'partner_negative_balance', COUNT(*) FROM partner WHERE balance < 0 OR balance_frozen < 0 OR balance_deposit < 0;
SELECT 'sys_info_demo_ip', COUNT(*) FROM sys_info WHERE id=1 AND sys_ip_w LIKE '%103.135.100.192%';
SELECT 'merchant_demo_ip', COUNT(*) FROM merchant WHERE ip LIKE '%103.135.100.192%' AND ip_df LIKE '%103.135.100.192%';
SELECT 'api_blacklisted', IF(COALESCE(api_ip_b, '') LIKE '%103.135.100.192%', 1, 0) FROM sys_info WHERE id=1;
SELECT 'ds_demo_marker', COUNT(*) FROM orders_ds WHERE code LIKE 'DSDEMO%' OR upi='demo@upi' OR realname='Demo Player';
SELECT 'df_demo_marker', COUNT(*) FROM orders_df WHERE code LIKE 'DFDEMO%' OR payment_bank='Demo Bank' OR payment_name LIKE 'Demo Receiver%';
SELECT 'ds_missing_payment', COUNT(*) FROM orders_ds o LEFT JOIN payment p ON p.id=o.payment_id WHERE o.status IN (-1,3,4) AND (o.payment_id IS NULL OR p.id IS NULL);
SELECT 'df_missing_payment', COUNT(*) FROM orders_df o LEFT JOIN payment p ON p.id=o.payment_id WHERE o.status IN (-1,-2,3,4) AND (o.payment_id IS NULL OR p.id IS NULL);
SELECT 'merchant_balance_record_last_mismatch', COUNT(*) FROM merchant m LEFT JOIN (SELECT br.user_id, br.change_after FROM balance_record br JOIN (SELECT user_id, MAX(id) id FROM balance_record WHERE user_type=1 GROUP BY user_id) t ON t.id=br.id) x ON x.user_id=m.id WHERE m.balance <> x.change_after OR x.change_after IS NULL;
SELECT 'partner_balance_record_last_mismatch', COUNT(*) FROM partner p LEFT JOIN (SELECT br.user_id, br.change_after FROM balance_record br JOIN (SELECT user_id, MAX(id) id FROM balance_record WHERE user_type=0 GROUP BY user_id) t ON t.id=br.id) x ON x.user_id=p.id WHERE p.balance <> x.change_after OR x.change_after IS NULL;
SELECT 'merchant_invalid_demo_mc_key', COUNT(*) FROM merchant WHERE mc_key IS NULL OR CHAR_LENGTH(mc_key) != 32 OR mc_key REGEXP '[^0-9a-f]';
SELECT 'merchant_invalid_demo_gg_key', COUNT(*) FROM merchant WHERE gg_key IS NULL OR CHAR_LENGTH(gg_key) != 16 OR gg_key REGEXP '[^A-Z2-7]';
SELECT 'merchant_duplicate_demo_mc_key', COUNT(*) - COUNT(DISTINCT mc_key) FROM merchant;
SELECT 'merchant_duplicate_demo_gg_key', COUNT(*) - COUNT(DISTINCT gg_key) FROM merchant;
SQL
```

`payment_active_count` 应为 0：脚本只保留历史收款资料用于订单闭环，不把收款资料放入在线卡池。
`api_blacklisted` 应为 0。API 侧当前按 `api_ip_b` 黑名单判断访问，不使用白名单字段。
`ds_demo_marker`、`df_demo_marker`、`ds_missing_payment`、`df_missing_payment`、两项 `*_balance_record_last_mismatch` 都应为 0。
四项 `merchant_*_demo_*key` 都应为 0：所有演示商户必须使用脚本随机生成的演示密钥，不能保留旧库真实密钥，也不能多个商户共用同一商户密钥或 Google 密钥。
