#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

load_default_env_file
require_d7pay_namespace_guard
require_command kubectl

if [ "${CONFIRM_D7PAY_ROLLBACK:-}" != "1" ]; then
  echo "回滚会影响 D7pay 线上实例。确认执行请追加 CONFIRM_D7PAY_ROLLBACK=1" >&2
  exit 1
fi

DEPLOYMENTS=(api-deploy admin-deploy merchant-deploy admin-h5-deploy merchant-h5-deploy apkdownload-deploy)
MODE="${D7PAY_ROLLBACK_MODE:-undo}"

case "${MODE}" in
  undo)
    print_section "执行 rollout undo"
    for deployment in "${DEPLOYMENTS[@]}"; do
      if kubectl get "deployment/${deployment}" -n "${KUBE_NAMESPACE}" >/dev/null 2>&1; then
        kubectl rollout undo "deployment/${deployment}" -n "${KUBE_NAMESPACE}"
        kubectl rollout status "deployment/${deployment}" -n "${KUBE_NAMESPACE}" --timeout=180s
      else
        echo "跳过不存在的 deployment: ${deployment}"
      fi
    done
    ;;
  scale-zero)
    print_section "缩容停用 D7pay"
    kubectl scale deployment "${DEPLOYMENTS[@]}" -n "${KUBE_NAMESPACE}" --replicas=0
    ;;
  *)
    echo "D7PAY_ROLLBACK_MODE 只支持 undo 或 scale-zero，当前为: ${MODE}" >&2
    exit 1
    ;;
esac

print_section "结果"
echo "D7pay rollback ${MODE} 已执行"
