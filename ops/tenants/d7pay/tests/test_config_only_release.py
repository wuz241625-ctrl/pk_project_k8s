import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[4]
DEPLOY_SCRIPT = ROOT / "ops/tenants/d7pay/jenkins/deploy-d7pay.sh"
APPLY_CONFIG_SCRIPT = ROOT / "ops/tenants/d7pay/scripts/apply-config.sh"


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


if __name__ == "__main__":
    unittest.main()
