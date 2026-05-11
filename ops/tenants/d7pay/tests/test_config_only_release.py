import pathlib
import unittest
from unittest.mock import patch

from ops.tenants.d7pay.scripts import render_app_config

ROOT = pathlib.Path(__file__).resolve().parents[4]
DEPLOY_SCRIPT = ROOT / "ops/tenants/d7pay/jenkins/deploy-d7pay.sh"
APPLY_CONFIG_SCRIPT = ROOT / "ops/tenants/d7pay/scripts/apply-config.sh"
RENDER_CONFIG_SCRIPT = ROOT / "ops/tenants/d7pay/scripts/render-config.sh"
D7PAY_K8S_DIR = ROOT / "ops/tenants/d7pay/k8s"
JENKINS_ENV_EXAMPLE = ROOT / "ops/tenants/d7pay/jenkins.env.example"
API_STATIC_DIR = ROOT / "api/static"


FORBIDDEN_BUILD_MARKERS = (
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
)


class D7payConfigOnlyReleaseTest(unittest.TestCase):
    def test_legacy_deploy_wrapper_does_not_build_or_rewrite_dockerfiles(self):
        text = DEPLOY_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("apply-config.sh", text)
        for marker in FORBIDDEN_BUILD_MARKERS:
            self.assertNotIn(marker, text)

    def test_apply_config_script_only_applies_tenant_configuration(self):
        text = APPLY_CONFIG_SCRIPT.read_text(encoding="utf-8")

        self.assertIn('PROJECT_DIR="${PROJECT_DIR:-${D7PAY_ROOT}}"', text)
        self.assertIn("app-configmap.yaml", text)
        self.assertIn("h5-configmaps.yaml", text)
        self.assertIn("services.yaml", text)
        self.assertIn("data-volumes.yaml", text)
        for marker in FORBIDDEN_BUILD_MARKERS:
            self.assertNotIn(marker, text)

    def test_rendered_nginx_exposes_api_static_assets_like_tc160(self):
        text = RENDER_CONFIG_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("location ^~ /static/", text)
        self.assertIn("proxy_pass http://127.0.0.1:31085/static/;", text)
        self.assertIn('add_header Cache-Control "public, immutable";', text)

    def test_api_static_contains_legacy_jquery_referenced_by_order_templates(self):
        jquery_path = API_STATIC_DIR / "v2/plugins/jquery/jquery-2.1.4.min.js"

        self.assertTrue(jquery_path.exists())
        self.assertIn("jQuery v2.1.4", jquery_path.read_text(encoding="utf-8", errors="ignore")[:200])

    def test_d7pay_config_keeps_business_time_utc_and_displays_pakistan_time(self):
        configmap = (D7PAY_K8S_DIR / "app-configmap.yaml").read_text(encoding="utf-8")

        self.assertIn("BUSINESS_TIMEZONE: UTC", configmap)
        self.assertIn("APP_DISPLAY_TIMEZONE: Asia/Karachi", configmap)
        self.assertNotIn("MYSQL_DEFAULT_TIME_ZONE", configmap)
        self.assertNotIn("TZ: Asia/Karachi", configmap)

    def test_d7pay_does_not_patch_mysql_or_redis_system_timezone(self):
        forbidden_manifests = (
            "mysql-timezone-configmaps.yaml",
            "mysql-timezone.patch.yaml",
            "mysql-slave-timezone.patch.yaml",
            "redis-timezone.patch.yaml",
            "admin-h5-timezone.patch.yaml",
            "merchant-h5-timezone.patch.yaml",
            "apkdownload-timezone.patch.yaml",
        )

        for filename in forbidden_manifests:
            self.assertFalse((D7PAY_K8S_DIR / filename).exists(), filename)

    def test_operations_docs_match_current_online_jenkins_release(self):
        operations = (ROOT / "ops/tenants/d7pay/README_OPERATIONS.md").read_text(encoding="utf-8")
        build_doc = (ROOT / "ops/tenants/d7pay/build.md").read_text(encoding="utf-8")
        runbook = (ROOT / "ops/tenants/d7pay/current-deployment-ops-runbook.md").read_text(encoding="utf-8")

        for doc in (operations, build_doc, runbook):
            self.assertIn("/opt/cicd/k8s_d7pay/sh/deploy-api.sh", doc)
            self.assertIn("/opt/cicd/k8s_d7pay/pk_project_k8s", doc)
            self.assertIn("git reset --hard origin/d7pay", doc)
            self.assertIn("Go worker 不属于当前线上发布入口", doc)
            self.assertIn("pakistanpay_v2.py", doc)
            self.assertIn("Jazzcashpay_v2.py", doc)
            self.assertIn("notify_df.py", doc)

    def test_jenkins_env_points_to_d7pay_workspace_and_timezone_contract(self):
        text = JENKINS_ENV_EXAMPLE.read_text(encoding="utf-8")

        self.assertIn("PROJECT_DIR=/opt/cicd/k8s_d7pay/pk_project_k8s", text)
        self.assertIn("BUSINESS_TIMEZONE=UTC", text)
        self.assertIn("APP_DISPLAY_TIMEZONE=Asia/Karachi", text)
        self.assertNotIn("PROJECT_DIR=/opt/cicd/k8s/pk_project_k8s", text)

    def test_config_render_reads_timezone_from_env_and_rejects_non_utc_business_time(self):
        source = D7PAY_K8S_DIR / "app-configmap.yaml"
        env = {
            "API_DOMAIN": "api.d7pay.net",
            "API_PUBLIC_SCHEME": "https",
            "BUSINESS_TIMEZONE": "UTC",
            "APP_DISPLAY_TIMEZONE": "Asia/Karachi",
        }

        with patch.dict("os.environ", env, clear=True):
            rendered = render_app_config.render(source)

        self.assertIn("BUSINESS_TIMEZONE: UTC", rendered)
        self.assertIn("APP_DISPLAY_TIMEZONE: Asia/Karachi", rendered)
        self.assertIn("API_OSPAY_API_HOST: https://api.d7pay.net/api", rendered)

        with patch.dict("os.environ", {**env, "BUSINESS_TIMEZONE": "Asia/Karachi"}, clear=True):
            with self.assertRaises(SystemExit):
                render_app_config.render(source)


if __name__ == "__main__":
    unittest.main()
