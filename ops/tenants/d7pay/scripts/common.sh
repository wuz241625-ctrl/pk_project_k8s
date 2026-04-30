#!/usr/bin/env bash

set -euo pipefail

D7PAY_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
D7PAY_TENANT_DIR="$(cd "${D7PAY_SCRIPT_DIR}/.." && pwd)"
D7PAY_ROOT="$(cd "${D7PAY_TENANT_DIR}/../../.." && pwd)"

d7pay_trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "${value}"
}

load_env_file() {
  local env_file="${1:-}"
  if [ -z "${env_file}" ]; then
    return 0
  fi
  if [ ! -f "${env_file}" ]; then
    echo "环境变量文件不存在: ${env_file}" >&2
    exit 1
  fi

  local line key value
  while IFS= read -r line || [ -n "${line}" ]; do
    line="${line%$'\r'}"
    if [[ -z "$(d7pay_trim "${line}")" || "${line}" =~ ^[[:space:]]*# ]]; then
      continue
    fi
    line="${line#export }"
    if [[ "${line}" != *=* ]]; then
      echo "环境变量文件存在无法解析的行: ${line}" >&2
      exit 1
    fi
    key="$(d7pay_trim "${line%%=*}")"
    value="$(d7pay_trim "${line#*=}")"
    if [[ ! "${key}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
      echo "环境变量名不合法: ${key}" >&2
      exit 1
    fi
    if [[ "${value}" == \"*\" && "${value}" == *\" ]]; then
      value="${value:1:${#value}-2}"
    elif [[ "${value}" == \'*\' && "${value}" == *\' ]]; then
      value="${value:1:${#value}-2}"
    fi
    export "${key}=${value}"
  done < "${env_file}"
}

load_default_env_file() {
  load_env_file "${D7PAY_ENV:-}"
}

has_command() {
  command -v "$1" >/dev/null 2>&1
}

require_command() {
  local name="$1"
  if ! has_command "${name}"; then
    echo "缺少命令: ${name}" >&2
    exit 1
  fi
}

require_env() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    echo "缺少环境变量: ${name}" >&2
    exit 1
  fi
}

reject_reserved_domain_value() {
  local name="$1"
  local value="${!name:-}"
  if [ -z "${value}" ]; then
    return 0
  fi
  case "${value}" in
    *\$*)
      echo "${name} 存在未展开的变量引用，不能用于发布: ${value}" >&2
      exit 1
      ;;
    *awekay.com*|*example.com*|*.example)
      echo "${name} 必须替换为 D7pay 客户自有域名，当前值不能用于发布: ${value}" >&2
      exit 1
      ;;
  esac
}

require_customer_domain() {
  local name="$1"
  require_env "${name}"
  reject_reserved_domain_value "${name}"
}

require_d7pay_namespace_guard() {
  KUBE_NAMESPACE="${KUBE_NAMESPACE:-pk-d7pay}"
  if [ "${KUBE_NAMESPACE}" = "pk" ] || [ "${KUBE_NAMESPACE}" = "default" ]; then
    echo "KUBE_NAMESPACE=${KUBE_NAMESPACE} 不允许用于 D7pay 运维命令" >&2
    exit 1
  fi
}

print_section() {
  printf '\n%s\n' "== $1 =="
}
