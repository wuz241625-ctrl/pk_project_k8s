#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

load_default_env_file

PROJECT_DIR="${PROJECT_DIR:-${D7PAY_ROOT}}"
TENANT_DIR="${PROJECT_DIR}/ops/tenants/d7pay"
KUBE_NAMESPACE="${KUBE_NAMESPACE:-pk-d7pay}"
KUBECONFIG="${KUBECONFIG:-/etc/kubernetes/admin.conf}"
export KUBECONFIG

require_command python3
require_command kubectl
require_customer_domain API_DOMAIN
require_customer_domain ADMIN_DOMAIN
require_customer_domain MERCHANT_DOMAIN
require_customer_domain APKDOWNLOAD_DOMAIN
reject_reserved_domain_value API_WEBSOCKET_ALLOW_HOST
reject_reserved_domain_value APP_API_BASE_URL
require_d7pay_namespace_guard

if [ -z "${D7PAY_RUNTIME_SECRET_YAML:-}" ]; then
  echo "缺少环境变量: D7PAY_RUNTIME_SECRET_YAML" >&2
  exit 1
fi
if [ ! -f "${D7PAY_RUNTIME_SECRET_YAML}" ]; then
  echo "D7PAY_RUNTIME_SECRET_YAML 指向的文件不存在: ${D7PAY_RUNTIME_SECRET_YAML}" >&2
  exit 1
fi

cd "${PROJECT_DIR}"

print_section "D7pay 合同检查"
python3 "${TENANT_DIR}/verify_release_contract.py"

print_section "D7pay 应用公共配置"
runtime_configmap="/tmp/d7pay-runtime-configmap.yaml"
python3 "${TENANT_DIR}/scripts/render_runtime_config.py" \
  --source "${TENANT_DIR}/k8s/runtime-configmap.yaml" \
  --output "${runtime_configmap}" >/dev/null

kubectl apply -f "${TENANT_DIR}/k8s/namespace.yaml"
kubectl apply -f "${runtime_configmap}"
kubectl apply -f "${TENANT_DIR}/k8s/h5-configmaps.yaml"
kubectl apply -f "${TENANT_DIR}/k8s/services.yaml"
kubectl apply -f "${D7PAY_RUNTIME_SECRET_YAML}"
kubectl apply -f "${TENANT_DIR}/k8s/data-volumes.yaml"

print_section "结果"
echo "D7pay 配置已检查并应用；应用构建和滚动发布请继续走现有发布脚本。"
