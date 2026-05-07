#!/usr/bin/env python3
import json
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[3]
D7PAY_DIR = ROOT / "ops" / "tenants" / "d7pay"


def read(relative_path):
    return (ROOT / relative_path).read_text(encoding="utf-8")


def require_file(relative_path):
    path = ROOT / relative_path
    if not path.exists():
        raise AssertionError(f"缺少文件: {relative_path}")


def require(text, needle, label):
    if needle not in text:
        raise AssertionError(f"{label} 缺少: {needle}")


def forbid(text, needle, label):
    if needle in text:
        raise AssertionError(f"{label} 禁止出现: {needle}")


def main():
    tenant = read("ops/tenants/d7pay/tenant.yaml")
    require(tenant, "namespace: pk-d7pay", "tenant.yaml")
    require(tenant, "mysql_database: pakistan_d7pay", "tenant.yaml")
    require(tenant, "business_timezone: UTC", "tenant.yaml")
    require(tenant, "display_timezone: Asia/Karachi", "tenant.yaml")
    require(tenant, "package_name: com.d7pay.merchant", "tenant.yaml")
    require(tenant, 'icon_resource: "@mipmap/ic_launcher_d7pay"', "tenant.yaml")
    require(tenant, "signing_policy: shared_release_keystore", "tenant.yaml")
    require(tenant, "config_py_policy: generated_from_config_example_or_secret_mount", "tenant.yaml")
    require(tenant, "domain_policy: customer_owned_required", "tenant.yaml")
    require(tenant, "public_api_service: api-public", "tenant.yaml")
    require(tenant, "api_public: 31085", "tenant.yaml")
    forbid(tenant, "awekay.com", "tenant.yaml")

    for asset in (
        "ops/tenants/d7pay/assets/d7pay-logo-source-app-1024.png",
        "ops/tenants/d7pay/assets/d7pay-logo-source-app-192.png",
        "ops/tenants/d7pay/assets/d7pay-logo-source-app-144.png",
        "ops/tenants/d7pay/assets/d7pay-logo-source-app-96.png",
        "ops/tenants/d7pay/assets/d7pay-logo-source-app-72.png",
        "ops/tenants/d7pay/assets/d7pay-logo-source-app-48.png",
        "ops/tenants/d7pay/assets/d7pay-logo-source-sidebar-128.png",
        "ops/tenants/d7pay/assets/d7pay-logo-source-download-192.png",
        "ops/tenants/d7pay/assets/d7pay-logo-source-favicon-256.png",
        "ops/tenants/d7pay/assets/d7pay-logo-source-favicon-64.png",
        "ops/tenants/d7pay/assets/d7pay-logo-source-favicon-48.png",
        "ops/tenants/d7pay/assets/d7pay-logo-source-favicon-32.png",
        "ops/tenants/d7pay/assets/d7pay-logo-source-favicon-16.png",
        "ops/tenants/d7pay/assets/d7pay-logo-mark-1024.png",
        "ops/tenants/d7pay/assets/d7pay-logo-full-1600x1200.png",
        "ops/tenants/d7pay/assets/d7pay-favicon.ico",
        "admin-h5/src/assets/brand/d7pay-logo-mark.png",
        "merchant-h5/src/assets/brand/d7pay-logo-mark.png",
        "apkdownload/src/assets/logo/d7pay-logo-192x192.png",
        "apkdownload/public/files/android/appInfo.d7pay.json",
        "Makefile",
        "build.md",
        "err.md",
        "ops/tenants/d7pay/README_OPERATIONS.md",
        "ops/tenants/d7pay/build.md",
        "ops/tenants/d7pay/err.md",
        "ops/tenants/d7pay/scripts/common.sh",
        "ops/tenants/d7pay/scripts/apply-config.sh",
        "ops/tenants/d7pay/scripts/build-flutter-app.sh",
        "ops/tenants/d7pay/scripts/preflight.sh",
        "ops/tenants/d7pay/scripts/render_app_config.py",
        "ops/tenants/d7pay/scripts/render-config.sh",
        "ops/tenants/d7pay/scripts/healthcheck.sh",
        "ops/tenants/d7pay/scripts/rollback.sh",
        "ops/tenants/d7pay/tests/test_config_only_release.py",
        "api/application/timezone.py",
        "admin/application/timezone.py",
        "merchant/application/timezone.py",
        "api/tests/test_timezone_policy.py",
        "admin/tests/test_timezone_policy.py",
        "merchant/tests/test_timezone_policy.py",
    ):
        require_file(asset)

    logo_generator = read("ops/tenants/d7pay/assets/generate_logo_assets.py")
    require(logo_generator, "D7pay logo assets generated from per-size image_gen sources", "generate_logo_assets.py")
    require(logo_generator, "app_48", "generate_logo_assets.py")
    require(logo_generator, "favicon_16", "generate_logo_assets.py")

    admin_logo = read("admin-h5/src/layout/components/Sidebar/Logo.vue")
    require(admin_logo, "d7pay-logo-mark.png", "admin Logo.vue")
    admin_settings = read("admin-h5/src/settings.js")
    require(admin_settings, "sidebarLogo: process.env.VUE_APP_SYSTEM === 'd7pay'", "admin settings.js")

    merchant_logo = read("merchant-h5/src/layout/components/Sidebar/Logo.vue")
    require(merchant_logo, "d7pay-logo-mark.png", "merchant Logo.vue")
    merchant_settings = read("merchant-h5/src/settings.js")
    require(merchant_settings, "sidebarLogo: process.env.VUE_APP_SYSTEM === 'd7pay'", "merchant settings.js")

    apk_view = read("apkdownload/src/views/apkm.vue")
    require(apk_view, "d7pay-logo-192x192.png", "apkdownload apkm.vue")
    apk_download = read("apkdownload/src/components/Appdownload/index.vue")
    require(apk_download, 'const appKey = import.meta.env.VITE_APP_KEY || "d7pay_merchant";', "apkdownload Appdownload.vue")
    require(apk_download, 'const legacyAppKey = import.meta.env.VITE_APP_FALLBACK_KEY || "d7pay_merchant";', "apkdownload Appdownload.vue")
    forbid(apk_download, '"lakshmi"', "apkdownload Appdownload.vue")
    forbid(apk_download, "ashrafi_merchant", "apkdownload Appdownload.vue")

    for env_file in ("apkdownload/.env", "apkdownload/.env.d7pay"):
        env_text = read(env_file)
        require(env_text, "VITE_APP_KEY=d7pay_merchant", env_file)
        require(env_text, "VITE_APP_FALLBACK_KEY=d7pay_merchant", env_file)
        forbid(env_text, "lakshmi", env_file)
        forbid(env_text, "ashrafi_merchant", env_file)

    for app_info_file in ("apkdownload/public/files/android/appInfo.json", "apkdownload/public/files/android/appInfo.d7pay.json"):
        app_info = json.loads(read(app_info_file))
        if set(app_info) != {"d7pay_merchant"}:
            raise AssertionError(f"{app_info_file} 只能包含 d7pay_merchant")
        app_info_text = read(app_info_file)
        forbid(app_info_text, "ashrafi", app_info_file)
        forbid(app_info_text, "lakshmi", app_info_file)

    for old_apk in (
        "apkdownload/public/files/android/ashrafi/ashrafi_v0.1.6_202604280158.apk",
        "apkdownload/public/files/android/lakshmi/lakshmi_v1.0.0.202406232042.apk",
    ):
        if (ROOT / old_apk).exists():
            raise AssertionError(f"D7pay 分支不允许保留旧客户 APK: {old_apk}")

    for removed_dead_path in (
        "api/jobs/freecharge-monitor/php",
        "api/application/app/login/banks/gcash_bank.py",
        "api/application/app/login/banks/indus_bank.py",
        "api/docker",
        "api/jobs/induspay",
        "api/jobs/jio",
        "api/jobs/maha",
        "merchant/.config.py.swp",
    ):
        if (ROOT / removed_dead_path).exists():
            raise AssertionError(f"D7pay 分支不允许保留旧银行死代码或旧制品: {removed_dead_path}")

    jenkins = read("ops/tenants/d7pay/jenkins.env.example")
    require(jenkins, "KUBE_NAMESPACE=pk-d7pay", "jenkins.env.example")
    require(jenkins, "RUN_ENV=PROD", "jenkins.env.example")
    require(jenkins, "BUSINESS_TIMEZONE=UTC", "jenkins.env.example")
    require(jenkins, "APP_DISPLAY_TIMEZONE=Asia/Karachi", "jenkins.env.example")
    require(jenkins, "APP_APPLICATION_ID=com.d7pay.merchant", "jenkins.env.example")
    require(jenkins, "APP_ICON=@mipmap/ic_launcher_d7pay", "jenkins.env.example")
    require(jenkins, "APP_SIGNING_MODE=shared_release_keystore", "jenkins.env.example")
    require(jenkins, "REQUIRE_RELEASE_SIGNING=true", "jenkins.env.example")
    require(jenkins, "D7PAY_GIT_BRANCH=d7pay", "jenkins.env.example")
    require(jenkins, "D7PAY_SECRET_YAML=", "jenkins.env.example")
    require(jenkins, "API_PUBLIC_NODEPORT=31085", "jenkins.env.example")
    require(jenkins, "API_PUBLIC_SCHEME=http", "jenkins.env.example")
    require(jenkins, "API_WEBSOCKET_ALLOW_HOST=api.d7pay.example.com", "jenkins.env.example")
    require(jenkins, "APP_API_BASE_URL=http://api.d7pay.example.com", "jenkins.env.example")
    require(jenkins, "D7pay 配置检查脚本会拒绝 example.com 和 awekay.com", "jenkins.env.example")
    require(jenkins, "FLUTTER_APP_DIR=", "jenkins.env.example")
    require(jenkins, "FLUTTER_BIN=", "jenkins.env.example")
    require(jenkins, "PROJECT_DIR=/opt/cicd/k8s_d7pay/pk_project_k8s", "jenkins.env.example")
    forbid(jenkins, "PROJECT_DIR=/opt/cicd/k8s/pk_project_k8s", "jenkins.env.example")
    forbid(jenkins.replace("D7pay 配置检查脚本会拒绝 example.com 和 awekay.com", ""), "awekay.com", "jenkins.env.example")

    handoff = read("docs/rental/d7pay-hosted.md")
    require(handoff, "APP_ICON=@mipmap/ic_launcher_d7pay", "d7pay-hosted.md")
    require(handoff, "ops/tenants/d7pay/README_OPERATIONS.md", "d7pay-hosted.md")
    require(handoff, "make d7pay-preflight", "d7pay-hosted.md")
    require(handoff, "make d7pay-apply-config", "d7pay-hosted.md")
    require(handoff, "make d7pay-build-app", "d7pay-hosted.md")
    ops_runbook = read("ops/tenants/d7pay/current-deployment-ops-runbook.md")
    require(ops_runbook, "APP_ICON=@mipmap/ic_launcher_d7pay", "current-deployment-ops-runbook.md")
    require(ops_runbook, "ops/tenants/d7pay/README_OPERATIONS.md", "current-deployment-ops-runbook.md")
    require(ops_runbook, "make d7pay-apply-config", "current-deployment-ops-runbook.md")
    require(ops_runbook, "make d7pay-build-app", "current-deployment-ops-runbook.md")
    require(ops_runbook, "现有发布脚本", "current-deployment-ops-runbook.md")

    operations_readme = read("ops/tenants/d7pay/README_OPERATIONS.md")
    require(operations_readme, "当前线上发布只走 Jenkins", "README_OPERATIONS.md")
    require(operations_readme, "PROJECT_DIR=/opt/cicd/k8s_d7pay/pk_project_k8s", "README_OPERATIONS.md")
    require(operations_readme, "BUSINESS_TIMEZONE=UTC", "README_OPERATIONS.md")
    require(operations_readme, "APP_DISPLAY_TIMEZONE=Asia/Karachi", "README_OPERATIONS.md")
    require(operations_readme, "bash ops/tenants/d7pay/scripts/apply-config.sh", "README_OPERATIONS.md")
    require(operations_readme, "现有发布脚本", "README_OPERATIONS.md")
    require(operations_readme, "不能把 D7pay 指到 `awekay.com`", "README_OPERATIONS.md")

    makefile = read("Makefile")
    for target in (
        "d7pay-preflight",
        "d7pay-render-config",
        "d7pay-apply-config",
        "d7pay-build-app",
        "d7pay-deploy",
        "d7pay-deploy-service",
        "d7pay-deploy-api",
        "d7pay-deploy-admin",
        "d7pay-deploy-merchant",
        "d7pay-deploy-admin-h5",
        "d7pay-deploy-merchant-h5",
        "d7pay-deploy-apkdownload",
        "d7pay-healthcheck",
        "d7pay-rollback",
    ):
        require(makefile, target, "Makefile")
    require(makefile, "d7pay-deploy-service 现在只做 D7pay 配置应用", "Makefile")

    common_script = read("ops/tenants/d7pay/scripts/common.sh")
    require(common_script, "load_env_file", "common.sh")
    require(common_script, "require_d7pay_namespace_guard", "common.sh")
    require(common_script, "reject_reserved_domain_value", "common.sh")
    require(common_script, "存在未展开的变量引用", "common.sh")

    app_build_script = read("ops/tenants/d7pay/scripts/build-flutter-app.sh")
    require(app_build_script, "ORG_GRADLE_PROJECT_appApplicationId", "build-flutter-app.sh")
    require(app_build_script, "ORG_GRADLE_PROJECT_requireReleaseSigning", "build-flutter-app.sh")
    require(app_build_script, "APP_API_BASE_URL", "build-flutter-app.sh")
    require(app_build_script, "appInfo.d7pay.json", "build-flutter-app.sh")
    require(app_build_script, "现有发布脚本发布 apkdownload", "build-flutter-app.sh")

    apply_config_script = read("ops/tenants/d7pay/scripts/apply-config.sh")
    require(apply_config_script, "load_default_env_file", "apply-config.sh")
    require(apply_config_script, 'PROJECT_DIR="${PROJECT_DIR:-${D7PAY_ROOT}}"', "apply-config.sh")
    require(apply_config_script, "require_customer_domain API_DOMAIN", "apply-config.sh")
    require(apply_config_script, "D7PAY_SECRET_YAML", "apply-config.sh")
    require(apply_config_script, "app-configmap.yaml", "apply-config.sh")
    require(apply_config_script, "h5-configmaps.yaml", "apply-config.sh")
    require(apply_config_script, "services.yaml", "apply-config.sh")
    require(apply_config_script, "data-volumes.yaml", "apply-config.sh")

    deploy_script = read("ops/tenants/d7pay/jenkins/deploy-d7pay.sh")
    require(deploy_script, "apply-config.sh", "deploy-d7pay.sh")
    require(deploy_script, "配置应用兼容入口", "deploy-d7pay.sh")
    for forbidden in (
        "docker build",
        "docker push",
        "Dockerfile",
        "RUN pnpm",
        "pnpm build",
        "pnpm run",
        "kubectl patch deployment",
        "patch_namespace_and_image",
        "build_h5_service",
        "build_apkdownload",
        "build_python_service",
    ):
        forbid(deploy_script, forbidden, "deploy-d7pay.sh")
        forbid(apply_config_script, forbidden, "apply-config.sh")
    forbid(deploy_script, "git reset --hard", "deploy-d7pay.sh")
    forbid(deploy_script, "git clean -fd", "deploy-d7pay.sh")

    preflight_script = read("ops/tenants/d7pay/scripts/preflight.sh")
    require(preflight_script, "verify_release_contract.py", "preflight.sh")
    require(preflight_script, "ops.tenants.d7pay.tests.test_config_only_release", "preflight.sh")
    require(preflight_script, "apply-config.sh", "preflight.sh")
    require(preflight_script, "build-flutter-app.sh", "preflight.sh")
    require(preflight_script, "D7PAY_SECRET_YAML", "preflight.sh")
    require(preflight_script, "replace-in-jenkins", "preflight.sh")

    render_script = read("ops/tenants/d7pay/scripts/render-config.sh")
    require(render_script, "nginx-d7pay.conf", "render-config.sh")
    require(render_script, "app-configmap.yaml", "render-config.sh")

    render_app_config = read("ops/tenants/d7pay/scripts/render_app_config.py")
    require(render_app_config, "BUSINESS_TIMEZONE 必须保持 UTC", "render_app_config.py")
    require(render_app_config, "API_PUBLIC_SCHEME", "render_app_config.py")
    require(render_app_config, "API_OSPAY_API_HOST", "render_app_config.py")

    healthcheck_script = read("ops/tenants/d7pay/scripts/healthcheck.sh")
    require(healthcheck_script, "kubectl rollout status", "healthcheck.sh")
    require(healthcheck_script, "curl", "healthcheck.sh")

    rollback_script = read("ops/tenants/d7pay/scripts/rollback.sh")
    require(rollback_script, "CONFIRM_D7PAY_ROLLBACK=1", "rollback.sh")
    require(rollback_script, "scale-zero", "rollback.sh")

    configmap = read("ops/tenants/d7pay/k8s/app-configmap.yaml")
    require(configmap, "RUN_ENV: PROD", "app-configmap.yaml")
    require(configmap, "BUSINESS_TIMEZONE: UTC", "app-configmap.yaml")
    require(configmap, "APP_DISPLAY_TIMEZONE: Asia/Karachi", "app-configmap.yaml")
    require(configmap, "MYSQL_DATABASE: pakistan_d7pay", "app-configmap.yaml")
    require(configmap, "API_OSPAY_API_HOST: http://api.d7pay.example.com/api", "app-configmap.yaml")
    forbid(configmap, "awekay.com", "app-configmap.yaml")
    forbid(configmap, "MYSQL_DEFAULT_TIME_ZONE", "app-configmap.yaml")
    forbid(configmap, "TZ: Asia/Karachi", "app-configmap.yaml")

    for service in ("api", "admin", "merchant"):
        config_example = read(f"{service}/config.example.py")
        require(config_example, 'business_timezone=_env("BUSINESS_TIMEZONE", "UTC")', f"{service}/config.example.py")
        require(config_example, 'display_timezone=_env("APP_DISPLAY_TIMEZONE", "Asia/Karachi")', f"{service}/config.example.py")

    for forbidden_timezone_manifest in (
        "ops/tenants/d7pay/k8s/mysql-timezone-configmaps.yaml",
        "ops/tenants/d7pay/k8s/mysql-timezone.patch.yaml",
        "ops/tenants/d7pay/k8s/mysql-slave-timezone.patch.yaml",
        "ops/tenants/d7pay/k8s/redis-timezone.patch.yaml",
        "ops/tenants/d7pay/k8s/admin-h5-timezone.patch.yaml",
        "ops/tenants/d7pay/k8s/merchant-h5-timezone.patch.yaml",
        "ops/tenants/d7pay/k8s/apkdownload-timezone.patch.yaml",
    ):
        if (ROOT / forbidden_timezone_manifest).exists():
            raise AssertionError(f"D7pay 不允许通过 K8s patch 修改系统时区: {forbidden_timezone_manifest}")

    services = read("ops/tenants/d7pay/k8s/services.yaml")
    require(services, "namespace: pk-d7pay", "services.yaml")
    require(services, "name: api-public", "services.yaml")
    require(services, "nodePort: 31085", "services.yaml")
    require(services, "nodePort: 31081", "services.yaml")
    require(services, "nodePort: 31082", "services.yaml")
    require(services, "nodePort: 31080", "services.yaml")

    h5_configmaps = read("ops/tenants/d7pay/k8s/h5-configmaps.yaml")
    require(h5_configmaps, "namespace: pk-d7pay", "h5-configmaps.yaml")
    require(h5_configmaps, "root /usr/share/nginx/html/d7pay/;", "h5-configmaps.yaml")
    require(h5_configmaps, "proxy_pass http://admin:6000/", "h5-configmaps.yaml")
    require(h5_configmaps, "proxy_pass http://merchant:8000/", "h5-configmaps.yaml")
    require(h5_configmaps, "name: download-nginx-conf", "h5-configmaps.yaml")

    for service in ("api", "admin", "merchant"):
        patch = read(f"ops/tenants/d7pay/k8s/{service}-deployment-env.patch.yaml")
        require(patch, "d7pay-config", f"{service} patch")
        require(patch, "d7pay-secret", f"{service} patch")

    api_patch = read("ops/tenants/d7pay/k8s/api-deployment-env.patch.yaml")
    require(api_patch, "mountPath: /fingerprint", "api patch")
    require(api_patch, "claimName: d7pay-fingerprint-pvc", "api patch")

    apk_patch = read("ops/tenants/d7pay/k8s/apkdownload-deployment-env.patch.yaml")
    require(apk_patch, "claimName: d7pay-apkdownload-pvc", "apkdownload patch")

    for service in ("api", "admin", "merchant"):
        config_example = read(f"{service}/config.example.py")
        require(config_example, 'tenant_code=_env("TENANT_CODE", "d7pay")', f"{service}/config.example.py")
        require(config_example, 'mysql_database=_env("MYSQL_DATABASE", "pakistan_d7pay")', f"{service}/config.example.py")
        require(config_example, "def get_config():", f"{service}/config.example.py")
        require(config_example, "return _base_config()", f"{service}/config.example.py")
        forbid(config_example, "DEV", f"{service}/config.example.py")
        forbid(config_example, "product = _base_config()", f"{service}/config.example.py")

    api_config = read("api/config.example.py")
    require(api_config, 'ospay_api_host=_env("API_OSPAY_API_HOST"', "api/config.example.py")
    require(api_config, 'websocket_api_allow_host=_env_list(', "api/config.example.py")

    print("D7pay release contract OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
