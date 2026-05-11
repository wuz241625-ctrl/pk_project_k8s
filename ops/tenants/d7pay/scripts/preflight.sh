#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

load_default_env_file
require_d7pay_namespace_guard
require_command python3
require_command git

cd "${D7PAY_ROOT}"

print_section "本地合同检查"
python3 -m py_compile \
  ops/tenants/d7pay/verify_release_contract.py \
  ops/tenants/d7pay/assets/generate_logo_assets.py \
  ops/tenants/d7pay/scripts/render_app_config.py \
  ops/tenants/d7pay/tests/test_config_only_release.py
python3 ops/tenants/d7pay/verify_release_contract.py

print_section "配置-only 发布边界测试"
python3 -m unittest ops.tenants.d7pay.tests.test_config_only_release

print_section "Shell 脚本语法检查"
for script in \
  ops/tenants/d7pay/jenkins/deploy-d7pay.sh \
  ops/tenants/d7pay/scripts/common.sh \
  ops/tenants/d7pay/scripts/apply-config.sh \
  ops/tenants/d7pay/scripts/build-flutter-app.sh \
  ops/tenants/d7pay/scripts/preflight.sh \
  ops/tenants/d7pay/scripts/render-config.sh \
  ops/tenants/d7pay/scripts/healthcheck.sh \
  ops/tenants/d7pay/scripts/rollback.sh \
  ops/tenants/d7pay/runtime/api-start-web-only.sh
do
  bash -n "${script}"
done

print_section "YAML 结构检查"
if python3 - <<'PY' >/tmp/d7pay-yaml-check.out 2>/tmp/d7pay-yaml-check.err
import pathlib
import yaml

for path in sorted(pathlib.Path("ops/tenants/d7pay/k8s").glob("*.yaml")):
    with path.open(encoding="utf-8") as handle:
        list(yaml.safe_load_all(handle))
print("D7pay k8s yaml parse OK")
PY
then
  cat /tmp/d7pay-yaml-check.out
else
  echo "未安装 PyYAML 或 YAML 解析失败，请在 Jenkins 镜像安装 PyYAML 后重试" >&2
  cat /tmp/d7pay-yaml-check.err >&2 || true
  exit 1
fi

print_section "域名防混用检查"
for name in API_DOMAIN ADMIN_DOMAIN MERCHANT_DOMAIN APKDOWNLOAD_DOMAIN API_WEBSOCKET_ALLOW_HOST APP_API_BASE_URL; do
  if [ -n "${!name:-}" ]; then
    reject_reserved_domain_value "${name}"
    echo "${name}=${!name}"
  else
    echo "${name}=未设置，Jenkins 正式发布前必须设置"
  fi
done

print_section "Secret 文件检查"
if [ -n "${D7PAY_SECRET_YAML:-}" ]; then
  if [ ! -f "${D7PAY_SECRET_YAML}" ]; then
    echo "D7PAY_SECRET_YAML 指向的文件不存在: ${D7PAY_SECRET_YAML}" >&2
    exit 1
  fi
  if grep -E "CHANGE_ME|replace-in-jenkins|example.com|awekay.com" "${D7PAY_SECRET_YAML}" >/dev/null; then
    echo "真实 Secret 文件仍包含占位值或禁用域名: ${D7PAY_SECRET_YAML}" >&2
    exit 1
  fi
  echo "Secret 文件存在且未发现占位值"
else
  echo "未设置 D7PAY_SECRET_YAML，跳过真实 Secret 文件检查"
fi

print_section "集群只读检查"
if has_command kubectl && [ -n "${KUBECONFIG:-}" ] && [ -f "${KUBECONFIG}" ]; then
  kubectl get ns pk >/dev/null
  kubectl get ns "${KUBE_NAMESPACE}" >/dev/null 2>&1 || true
  kubectl get svc -n pk >/dev/null
  echo "kubectl 可访问，现有 pk namespace 可读"
else
  echo "未检测到可用 kubectl/KUBECONFIG，跳过集群只读检查"
fi

print_section "结果"
echo "D7pay preflight OK"
