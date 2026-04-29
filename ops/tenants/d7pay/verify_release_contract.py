#!/usr/bin/env python3
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[3]
D7PAY_DIR = ROOT / "ops" / "tenants" / "d7pay"


def read(relative_path):
    return (ROOT / relative_path).read_text(encoding="utf-8")


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
    require(tenant, "package_name: com.d7pay.merchant", "tenant.yaml")
    require(tenant, "signing_policy: shared_release_keystore", "tenant.yaml")
    require(tenant, "config_py_policy: generated_from_config_example_or_secret_mount", "tenant.yaml")
    require(tenant, "domain_policy: customer_owned_required", "tenant.yaml")
    require(tenant, "public_api_service: api-public", "tenant.yaml")
    require(tenant, "api_public: 31085", "tenant.yaml")
    forbid(tenant, "awekay.com", "tenant.yaml")

    jenkins = read("ops/tenants/d7pay/jenkins.env.example")
    require(jenkins, "KUBE_NAMESPACE=pk-d7pay", "jenkins.env.example")
    require(jenkins, "RUN_ENV=PROD", "jenkins.env.example")
    require(jenkins, "APP_APPLICATION_ID=com.d7pay.merchant", "jenkins.env.example")
    require(jenkins, "APP_SIGNING_MODE=shared_release_keystore", "jenkins.env.example")
    require(jenkins, "REQUIRE_RELEASE_SIGNING=true", "jenkins.env.example")
    require(jenkins, "D7PAY_RUNTIME_SECRET_YAML=", "jenkins.env.example")
    require(jenkins, "API_PUBLIC_NODEPORT=31085", "jenkins.env.example")
    require(jenkins, "API_PUBLIC_SCHEME=http", "jenkins.env.example")
    require(jenkins, "APP_API_BASE_URL=${API_PUBLIC_SCHEME}://${API_DOMAIN}", "jenkins.env.example")
    require(jenkins, "deploy-d7pay.sh 会拒绝 example.com 和 awekay.com", "jenkins.env.example")
    forbid(jenkins.replace("deploy-d7pay.sh 会拒绝 example.com 和 awekay.com", ""), "awekay.com", "jenkins.env.example")

    deploy_script = read("ops/tenants/d7pay/jenkins/deploy-d7pay.sh")
    require(deploy_script, "KUBE_NAMESPACE", "deploy-d7pay.sh")
    require(deploy_script, "require_customer_domain API_DOMAIN", "deploy-d7pay.sh")
    require(deploy_script, "reject_reserved_domain_value API_WEBSOCKET_ALLOW_HOST", "deploy-d7pay.sh")
    require(deploy_script, "render_runtime_configmap", "deploy-d7pay.sh")
    require(deploy_script, "API_PUBLIC_SCHEME", "deploy-d7pay.sh")
    require(deploy_script, "h5-configmaps.yaml", "deploy-d7pay.sh")
    require(deploy_script, "services.yaml", "deploy-d7pay.sh")
    require(deploy_script, "build_h5_service admin-h5 admin-h5-deploy", "deploy-d7pay.sh")
    require(deploy_script, "pnpm run build:d7pay", "deploy-d7pay.sh")

    configmap = read("ops/tenants/d7pay/k8s/runtime-configmap.yaml")
    require(configmap, "RUN_ENV: PROD", "runtime-configmap.yaml")
    require(configmap, "MYSQL_DATABASE: pakistan_d7pay", "runtime-configmap.yaml")
    require(configmap, "API_OSPAY_API_HOST: http://api.d7pay.example.com/api", "runtime-configmap.yaml")
    forbid(configmap, "awekay.com", "runtime-configmap.yaml")

    services = read("ops/tenants/d7pay/k8s/services.yaml")
    require(services, "namespace: pk-d7pay", "services.yaml")
    require(services, "name: api-public", "services.yaml")
    require(services, "nodePort: 31085", "services.yaml")
    require(services, "nodePort: 31081", "services.yaml")
    require(services, "nodePort: 31082", "services.yaml")
    require(services, "nodePort: 31080", "services.yaml")

    h5_configmaps = read("ops/tenants/d7pay/k8s/h5-configmaps.yaml")
    require(h5_configmaps, "namespace: pk-d7pay", "h5-configmaps.yaml")
    require(h5_configmaps, "proxy_pass http://admin:6000/", "h5-configmaps.yaml")
    require(h5_configmaps, "proxy_pass http://merchant:8000/", "h5-configmaps.yaml")
    require(h5_configmaps, "name: download-nginx-conf", "h5-configmaps.yaml")

    for service in ("api", "admin", "merchant"):
        patch = read(f"ops/tenants/d7pay/k8s/{service}-deployment-env.patch.yaml")
        require(patch, "d7pay-runtime-config", f"{service} patch")
        require(patch, "d7pay-runtime-secret", f"{service} patch")

    api_patch = read("ops/tenants/d7pay/k8s/api-deployment-env.patch.yaml")
    require(api_patch, "mountPath: /fingerprint", "api patch")
    require(api_patch, "claimName: d7pay-fingerprint-pvc", "api patch")

    apk_patch = read("ops/tenants/d7pay/k8s/apkdownload-deployment-env.patch.yaml")
    require(apk_patch, "claimName: d7pay-apkdownload-pvc", "apkdownload patch")

    for service in ("api", "admin", "merchant"):
        config_example = read(f"{service}/config.example.py")
        require(config_example, 'tenant_code=_env("TENANT_CODE", "local")', f"{service}/config.example.py")
        require(config_example, 'mysql_database=_env("MYSQL_DATABASE", "pakistan")', f"{service}/config.example.py")

    api_config = read("api/config.example.py")
    require(api_config, 'ospay_api_host=_env("API_OSPAY_API_HOST"', "api/config.example.py")
    require(api_config, 'websocket_api_allow_host=_env_list(', "api/config.example.py")

    print("D7pay release contract OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
