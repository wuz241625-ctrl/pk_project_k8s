import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[4]
DEPLOY_SCRIPT = ROOT / "ops/tenants/d7pay/jenkins/deploy-d7pay.sh"
APPLY_CONFIG_SCRIPT = ROOT / "ops/tenants/d7pay/scripts/apply-config.sh"
D7PAY_K8S_DIR = ROOT / "ops/tenants/d7pay/k8s"


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

        self.assertIn("runtime-configmap.yaml", text)
        self.assertIn("h5-configmaps.yaml", text)
        self.assertIn("services.yaml", text)
        self.assertIn("data-volumes.yaml", text)
        for marker in FORBIDDEN_BUILD_MARKERS:
            self.assertNotIn(marker, text)

    def test_d7pay_runtime_keeps_business_time_utc_and_displays_pakistan_time(self):
        configmap = (D7PAY_K8S_DIR / "runtime-configmap.yaml").read_text(encoding="utf-8")

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


if __name__ == "__main__":
    unittest.main()
