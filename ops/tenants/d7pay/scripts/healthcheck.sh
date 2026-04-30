#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

load_default_env_file
require_d7pay_namespace_guard
require_command curl

require_customer_domain API_DOMAIN
require_customer_domain ADMIN_DOMAIN
require_customer_domain MERCHANT_DOMAIN
require_customer_domain APKDOWNLOAD_DOMAIN

print_section "K8s rollout 检查"
if has_command kubectl && [ -n "${KUBECONFIG:-}" ] && [ -f "${KUBECONFIG}" ]; then
  for deployment in api-deploy admin-deploy merchant-deploy admin-h5-deploy merchant-h5-deploy apkdownload-deploy; do
    kubectl rollout status "deployment/${deployment}" -n "${KUBE_NAMESPACE}" --timeout=180s
  done
else
  echo "未检测到可用 kubectl/KUBECONFIG，跳过 K8s rollout 检查"
fi

check_url() {
  local label="$1"
  local url="$2"
  local status
  status="$(curl -k -L -sS -o /dev/null -w "%{http_code}" --max-time 15 "${url}" || true)"
  if [ "${status}" = "000" ] || [ "${status}" -ge 500 ]; then
    echo "${label} 不健康: ${url} HTTP ${status}" >&2
    exit 1
  fi
  echo "${label} OK: ${url} HTTP ${status}"
}

SCHEME="${API_PUBLIC_SCHEME:-http}"

print_section "域名连通检查"
check_url "admin" "${SCHEME}://${ADMIN_DOMAIN}/"
check_url "merchant" "${SCHEME}://${MERCHANT_DOMAIN}/"
check_url "apkdownload" "${SCHEME}://${APKDOWNLOAD_DOMAIN}/"
check_url "api" "${SCHEME}://${API_DOMAIN}/api/"

print_section "结果"
echo "D7pay healthcheck OK"
