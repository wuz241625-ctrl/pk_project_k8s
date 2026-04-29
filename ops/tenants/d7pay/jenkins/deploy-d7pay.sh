#!/usr/bin/env bash
set -euo pipefail

# Jenkins 入口脚本示例：在服务器 /opt/cicd/k8s 上按 D7pay 租户发布。
# 真实环境变量从 Jenkins Credentials 注入，默认值只用于说明合同。

PROJECT_DIR="${PROJECT_DIR:-/opt/cicd/k8s/pk_project_k8s}"
K8S_ROOT="${K8S_ROOT:-/opt/cicd/k8s}"
REGISTRY="${REGISTRY:-10.170.0.18:30086/lib}"
TENANT_DIR="${PROJECT_DIR}/ops/tenants/d7pay"
KUBE_NAMESPACE="${KUBE_NAMESPACE:-pk-d7pay}"
KUBECONFIG="${KUBECONFIG:-/etc/kubernetes/admin.conf}"
IMAGE_TAG="${IMAGE_TAG:-d7pay-$(date +%Y%m%d%H%M%S)}"

export KUBECONFIG

require_env() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    echo "缺少环境变量: ${name}" >&2
    exit 1
  fi
}

patch_namespace_and_image() {
  local source_yaml="$1"
  local target_yaml="$2"
  local image="$3"
  python3 - "$source_yaml" "$target_yaml" "$KUBE_NAMESPACE" "$image" <<'PY'
import pathlib
import sys

source, target, namespace, image = sys.argv[1:5]
text = pathlib.Path(source).read_text(encoding="utf-8")
lines = []
for line in text.splitlines():
    stripped = line.strip()
    if stripped.startswith("namespace:"):
        indent = line[: len(line) - len(line.lstrip())]
        lines.append(f"{indent}namespace: {namespace}")
    elif stripped.startswith("image:"):
        indent = line[: len(line) - len(line.lstrip())]
        lines.append(f"{indent}image: {image}")
    else:
        lines.append(line)
pathlib.Path(target).write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
}

sync_code() {
  cd "${PROJECT_DIR}"
  git fetch --all
  git reset --hard origin/main
  git clean -fd
}

apply_tenant_resources() {
  kubectl apply -f "${TENANT_DIR}/k8s/namespace.yaml"
  kubectl apply -f "${TENANT_DIR}/k8s/runtime-configmap.yaml"
  if [ -n "${D7PAY_RUNTIME_SECRET_YAML:-}" ]; then
    kubectl apply -f "${D7PAY_RUNTIME_SECRET_YAML}"
  else
    echo "D7PAY_RUNTIME_SECRET_YAML 未设置，只跳过真实 Secret apply" >&2
  fi
  kubectl apply -f "${TENANT_DIR}/k8s/data-volumes.yaml"
}

build_python_service() {
  local component="$1"
  local deployment="$2"
  local build_dir="${K8S_ROOT}/${component}/pk_dockerfile"
  local source_yaml="${K8S_ROOT}/${component}/k8s/${component}-deployment.yaml"
  local image="${REGISTRY}/${component}:${IMAGE_TAG}"
  local tmp_yaml="/tmp/d7pay-${component}-deployment.yaml"

  rm -rf "${build_dir:?}/${component}"
  cp -r "${PROJECT_DIR}/${component}" "${build_dir}/${component}"
  docker build -t "${image}" "${build_dir}"
  docker push "${image}"
  patch_namespace_and_image "${source_yaml}" "${tmp_yaml}" "${image}"
  kubectl apply -f "${tmp_yaml}"
  kubectl patch deployment "${deployment}" -n "${KUBE_NAMESPACE}" --type=strategic \
    --patch-file "${TENANT_DIR}/k8s/${component}-deployment-env.patch.yaml"
  kubectl rollout status "deployment/${deployment}" -n "${KUBE_NAMESPACE}" --timeout=180s
}

build_h5_service() {
  local component="$1"
  local deployment="$2"
  local build_script="$3"
  local build_dir="${K8S_ROOT}/${component}/pk_dockerfile"
  local source_yaml="${K8S_ROOT}/${component}/k8s/${component}-deployment.yaml"
  local image="${REGISTRY}/${component}:${IMAGE_TAG}"
  local tmp_yaml="/tmp/d7pay-${component}-deployment.yaml"

  rm -rf "${build_dir:?}/${component}"
  cp -r "${PROJECT_DIR}/${component}" "${build_dir}/${component}"
  python3 - "${build_dir}/Dockerfile" "${build_script}" <<'PY'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
script = sys.argv[2]
text = path.read_text(encoding="utf-8")
text = re.sub(r"RUN pnpm (run )?build:prod", f"RUN pnpm run {script}", text)
text = text.replace("ENV VUE_APP_SYSTEM=prod", "ENV VUE_APP_SYSTEM=d7pay")
path.write_text(text, encoding="utf-8")
PY
  docker build -t "${image}" "${build_dir}"
  docker push "${image}"
  patch_namespace_and_image "${source_yaml}" "${tmp_yaml}" "${image}"
  kubectl apply -f "${tmp_yaml}"
  kubectl rollout status "deployment/${deployment}" -n "${KUBE_NAMESPACE}" --timeout=180s
}

build_apkdownload() {
  local component="apkdownload"
  local deployment="apkdownload-deploy"
  local build_dir="${K8S_ROOT}/${component}/pk_dockerfile"
  local source_yaml="${K8S_ROOT}/${component}/k8s/${component}-deployment.yaml"
  local image="${REGISTRY}/${component}:${IMAGE_TAG}"
  local tmp_yaml="/tmp/d7pay-${component}-deployment.yaml"

  rm -rf "${build_dir:?}/${component}"
  cp -r "${PROJECT_DIR}/${component}" "${build_dir}/${component}"
  python3 - "${build_dir}/start.sh" <<'PY'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = text.replace("pnpm build", "pnpm run build:d7pay")
path.write_text(text, encoding="utf-8")
PY
  docker build -t "${image}" "${build_dir}"
  docker push "${image}"
  patch_namespace_and_image "${source_yaml}" "${tmp_yaml}" "${image}"
  kubectl apply -f "${tmp_yaml}"
  kubectl patch deployment "${deployment}" -n "${KUBE_NAMESPACE}" --type=strategic \
    --patch-file "${TENANT_DIR}/k8s/apkdownload-deployment-env.patch.yaml"
  kubectl rollout status "deployment/${deployment}" -n "${KUBE_NAMESPACE}" --timeout=180s
}

main() {
  require_env MYSQL_PASSWORD
  require_env API_KEY_ORDER
  require_env API_SECRET_KEY
  require_env ADMIN_COOKIE_KEY
  require_env ADMIN_ID_TOKEN_KEY
  require_env MERCHANT_COOKIE_KEY

  sync_code
  python3 "${TENANT_DIR}/verify_release_contract.py"
  apply_tenant_resources

  build_python_service api api-deploy
  build_python_service admin admin-deploy
  build_python_service merchant merchant-deploy
  build_h5_service admin-h5 admin-h5-deploy "${ADMIN_H5_BUILD_SCRIPT:-d7pay:prod}"
  build_h5_service merchant-h5 merchant-h5-deploy "${MERCHANT_H5_BUILD_SCRIPT:-d7pay:prod}"
  build_apkdownload
}

main "$@"
