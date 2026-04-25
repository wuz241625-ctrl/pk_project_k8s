# 演示数据整理脚本构建与执行

## 本地验证

```bash
cd /Users/tear/pk_project_k8s
python3 -m unittest ops/demo_data/test_prepare_demo_data.py -v
python3 -m py_compile ops/demo_data/prepare_demo_data.py
```

## 线上 dry-run

```bash
export KUBECONFIG=/etc/kubernetes/admin.conf
ADMIN_POD=$(kubectl get pods -n pk -l app=admin -o jsonpath='{.items[0].metadata.name}')
kubectl exec -i -n pk "$ADMIN_POD" -- sh -lc 'cat > /tmp/prepare_demo_data.py' < ops/demo_data/prepare_demo_data.py
kubectl exec -n pk "$ADMIN_POD" -- python /tmp/prepare_demo_data.py
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
kubectl exec -n pk demo-data-runner -- python /tmp/prepare_demo_data.py
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
SELECT 'payment_d', COUNT(*) FROM payment_d;
SELECT 'orders_ds', COUNT(*) FROM orders_ds;
SELECT 'orders_df', COUNT(*) FROM orders_df;
SELECT 'balance_record', COUNT(*) FROM balance_record;
SELECT 'merchant_target_payment_nonempty', COUNT(*) FROM merchant WHERE target_payment IS NOT NULL AND target_payment != '';
SELECT 'merchant_negative_balance', COUNT(*) FROM merchant WHERE balance < 0 OR balance_frozen < 0;
SELECT 'sys_info_demo_ip', COUNT(*) FROM sys_info WHERE id=1 AND sys_ip_w LIKE '%103.135.100.192%';
SELECT 'merchant_demo_ip', COUNT(*) FROM merchant WHERE ip LIKE '%103.135.100.192%' AND ip_df LIKE '%103.135.100.192%';
SQL
```
