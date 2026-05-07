#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

load_default_env_file
require_d7pay_namespace_guard
require_command python3

require_customer_domain API_DOMAIN
require_customer_domain ADMIN_DOMAIN
require_customer_domain MERCHANT_DOMAIN
require_customer_domain APKDOWNLOAD_DOMAIN
reject_reserved_domain_value API_WEBSOCKET_ALLOW_HOST
reject_reserved_domain_value APP_API_BASE_URL

RENDER_DIR="${D7PAY_RENDER_DIR:-/tmp/d7pay-rendered}"
mkdir -p "${RENDER_DIR}"

APP_CONFIGMAP="${RENDER_DIR}/app-configmap.yaml"
NGINX_CONFIG="${RENDER_DIR}/nginx-d7pay.conf"
SUMMARY_FILE="${RENDER_DIR}/env-summary.txt"

cd "${D7PAY_ROOT}"
python3 ops/tenants/d7pay/scripts/render_app_config.py --output "${APP_CONFIGMAP}"

cat > "${NGINX_CONFIG}" <<NGINX
server {
    listen 80;
    server_name ${ADMIN_DOMAIN};

    location / {
        proxy_pass http://127.0.0.1:31081;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}

server {
    listen 80;
    server_name ${MERCHANT_DOMAIN};

    location / {
        proxy_pass http://127.0.0.1:31082;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}

server {
    listen 80;
    server_name ${API_DOMAIN};

    location = / {
        return 404;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:31085/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}

server {
    listen 80;
    server_name ${APKDOWNLOAD_DOMAIN};

    location / {
        proxy_pass http://127.0.0.1:31080;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
NGINX

cat > "${SUMMARY_FILE}" <<SUMMARY
TENANT=d7pay
KUBE_NAMESPACE=${KUBE_NAMESPACE:-pk-d7pay}
API_DOMAIN=${API_DOMAIN}
ADMIN_DOMAIN=${ADMIN_DOMAIN}
MERCHANT_DOMAIN=${MERCHANT_DOMAIN}
APKDOWNLOAD_DOMAIN=${APKDOWNLOAD_DOMAIN}
API_PUBLIC_SCHEME=${API_PUBLIC_SCHEME:-http}
NODEPORT_ADMIN_H5=31081
NODEPORT_MERCHANT_H5=31082
NODEPORT_API_PUBLIC=31085
NODEPORT_APKDOWNLOAD=31080
FINGERPRINT_HOST_PATH=${FINGERPRINT_HOST_PATH:-/data/pk-d7pay/fingerprint}
APKDOWNLOAD_HOST_PATH=${APKDOWNLOAD_HOST_PATH:-/data/pk-d7pay/apkdownload/d7pay}
SUMMARY

echo "已渲染 D7pay 配置:"
echo "- ${APP_CONFIGMAP}"
echo "- ${NGINX_CONFIG}"
echo "- ${SUMMARY_FILE}"
