#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "deploy-d7pay.sh 已降级为 D7pay 配置应用兼容入口。"
echo "它不会构建镜像、不会推送镜像、不会改写打包文件；应用构建和滚动发布请走现有发布脚本。"

exec bash "${SCRIPT_DIR}/../scripts/apply-config.sh"
