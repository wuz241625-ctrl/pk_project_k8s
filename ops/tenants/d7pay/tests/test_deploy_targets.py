import pathlib
import shlex
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[4]
DEPLOY_SCRIPT = ROOT / "ops/tenants/d7pay/jenkins/deploy-d7pay.sh"


def run_bash(script):
    command = f"source {shlex.quote(str(DEPLOY_SCRIPT))}; {script}"
    return subprocess.run(
        ["bash", "-c", command],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )


class D7payDeployTargetsTest(unittest.TestCase):
    def test_default_target_expands_to_full_release_order(self):
        result = run_bash('set_deploy_targets ""; printf "%s\\n" "${SELECTED_DEPLOY_TARGETS[@]}"')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            ["api", "admin", "merchant", "admin-h5", "merchant-h5", "apkdownload"],
        )

    def test_comma_targets_are_deduplicated_in_first_seen_order(self):
        result = run_bash('set_deploy_targets "api,admin-h5 api"; printf "%s\\n" "${SELECTED_DEPLOY_TARGETS[@]}"')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["api", "admin-h5"])

    def test_invalid_target_fails_loudly(self):
        result = run_bash('set_deploy_targets "api,unknown-service"')

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("不支持的 D7pay 发布目标: unknown-service", result.stderr)
        self.assertIn("api admin merchant admin-h5 merchant-h5 apkdownload", result.stderr)

    def test_single_h5_target_dispatches_only_that_service(self):
        result = run_bash(
            """
            build_python_service() { echo "python:$1:$2"; }
            build_h5_service() { echo "h5:$1:$2:$3"; }
            build_apkdownload() { echo "apkdownload"; }
            set_deploy_targets "merchant-h5"
            deploy_selected_targets
            """
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("h5:merchant-h5:merchant-h5-deploy:d7pay:prod", result.stdout)
        self.assertNotIn("python:api", result.stdout)
        self.assertNotIn("python:admin", result.stdout)
        self.assertNotIn("apkdownload", result.stdout)


if __name__ == "__main__":
    unittest.main()
