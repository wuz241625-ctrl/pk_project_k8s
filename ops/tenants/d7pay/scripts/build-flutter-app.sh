#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

load_default_env_file

FLUTTER_APP_DIR="${FLUTTER_APP_DIR:-/Users/tear/pk_project/ashrafi_merchant_flutter}"
FLUTTER_BIN="${FLUTTER_BIN:-/Users/tear/sdk/flutter/bin/flutter}"
APKDOWNLOAD_ANDROID_DIR="${APKDOWNLOAD_ANDROID_DIR:-${D7PAY_ROOT}/apkdownload/public/files/android}"
APP_APK_KEY="${APP_APK_KEY:-d7pay_merchant}"
APP_DISPLAY_NAME="${APP_DISPLAY_NAME:-D7pay Merchant}"
APP_SHORT_NAME="${APP_SHORT_NAME:-D7pay}"
APP_APPLICATION_ID="${APP_APPLICATION_ID:-com.d7pay.merchant}"
APP_ICON="${APP_ICON:-@mipmap/ic_launcher_d7pay}"
REQUIRE_RELEASE_SIGNING="${REQUIRE_RELEASE_SIGNING:-true}"
API_PUBLIC_SCHEME="${API_PUBLIC_SCHEME:-https}"

if [ -z "${APP_API_BASE_URL:-}" ] && [ -n "${API_DOMAIN:-}" ]; then
  APP_API_BASE_URL="${API_PUBLIC_SCHEME}://${API_DOMAIN}"
fi

require_env APP_API_BASE_URL

if [ ! -d "${FLUTTER_APP_DIR}" ]; then
  echo "Flutter 项目目录不存在: ${FLUTTER_APP_DIR}" >&2
  exit 1
fi

if [ ! -x "${FLUTTER_BIN}" ] && has_command flutter; then
  FLUTTER_BIN="$(command -v flutter)"
fi

if [ ! -x "${FLUTTER_BIN}" ]; then
  echo "Flutter 命令不存在或不可执行: ${FLUTTER_BIN}" >&2
  exit 1
fi

if [ "${REQUIRE_RELEASE_SIGNING}" = "true" ] && [ ! -f "${FLUTTER_APP_DIR}/android/key.properties" ]; then
  echo "正式发布必须提供 ${FLUTTER_APP_DIR}/android/key.properties" >&2
  echo "如只做本地验证，可显式设置 REQUIRE_RELEASE_SIGNING=false" >&2
  exit 1
fi

version="$(
  python3 - "${FLUTTER_APP_DIR}/pubspec.yaml" <<'PY'
import pathlib
import re
import sys

text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
match = re.search(r"^version:\s*([^\s]+)", text, re.MULTILINE)
if not match:
    raise SystemExit("pubspec.yaml 缺少 version")
print(match.group(1))
PY
)"
version_name="${version%%+*}"
timestamp="${D7PAY_APP_BUILD_TIMESTAMP:-$(date +%Y%m%d%H%M)}"
apk_filename="${D7PAY_APP_APK_FILENAME:-d7pay_merchant_universal_v${version_name}_${timestamp}.apk}"
apk_dir="${APKDOWNLOAD_ANDROID_DIR}/d7pay"
apk_path="${apk_dir}/${apk_filename}"
app_info_path="${APKDOWNLOAD_ANDROID_DIR}/appInfo.d7pay.json"

print_section "构建 D7pay Flutter APK"
cd "${FLUTTER_APP_DIR}"
"${FLUTTER_BIN}" pub get
ORG_GRADLE_PROJECT_appLabel="${APP_DISPLAY_NAME}" \
ORG_GRADLE_PROJECT_appApplicationId="${APP_APPLICATION_ID}" \
ORG_GRADLE_PROJECT_appIcon="${APP_ICON}" \
ORG_GRADLE_PROJECT_requireReleaseSigning="${REQUIRE_RELEASE_SIGNING}" \
"${FLUTTER_BIN}" build apk --release \
  --target-platform android-arm,android-arm64 \
  -PtargetAbis=armeabi-v7a,arm64-v8a \
  --dart-define=API_BASE_URL="${APP_API_BASE_URL}" \
  --dart-define=APP_DISPLAY_NAME="${APP_DISPLAY_NAME}" \
  --dart-define=APP_SHORT_NAME="${APP_SHORT_NAME}"

source_apk="${FLUTTER_APP_DIR}/build/app/outputs/flutter-apk/app-release.apk"
if [ ! -f "${source_apk}" ]; then
  echo "未找到构建产物: ${source_apk}" >&2
  exit 1
fi

print_section "更新 apkdownload 制品"
mkdir -p "${apk_dir}"
cp "${source_apk}" "${apk_path}"

python3 - "${app_info_path}" "${APP_APK_KEY}" "${APP_DISPLAY_NAME}" "${version_name}" "${apk_filename}" "${apk_path}" <<'PY'
import json
import pathlib
import sys
from datetime import datetime

app_info_path, app_key, app_name, version, filename, apk_path = sys.argv[1:7]
path = pathlib.Path(app_info_path)
data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
size_mb = max(1, round(pathlib.Path(apk_path).stat().st_size / 1024 / 1024))
data[app_key] = {
    "name": app_name,
    "version": version,
    "filename": filename,
    "path": f"/files/android/d7pay/{filename}",
    "size": f"{size_mb} MB",
    "updateTime": datetime.now().strftime("%b %-d, %Y, %H:%M"),
    "compatibility": "Android 8+ ARM/ARM64",
    "language": "EN",
    "developer": "D7pay",
    "introduction": "D7pay merchant app for wallet onboarding, fingerprint activation, and payment account management.",
}
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

print_section "结果"
echo "APK: ${apk_path}"
echo "元信息: ${app_info_path}"
echo "下一步: git add apkdownload/public/files/android/appInfo.d7pay.json apkdownload/public/files/android/d7pay/${apk_filename}"
echo "提交推送后由现有发布脚本发布 apkdownload。"
