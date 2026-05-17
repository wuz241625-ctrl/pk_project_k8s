import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPO_ROOT / "api"
GO_WORKER_ROOT = Path("/Users/tear/pk-go-worker")


class EasyPaisaTimeOutGuardRetirementTests(unittest.TestCase):
    def test_python_timeout_guard_class_is_retired(self):
        source = (API_ROOT / "jobs" / "time_out.py").read_text(encoding="utf-8")

        self.assertNotIn("class " + "TimeOutGuard", source)
        self.assertNotIn("INDEX_" + "DISPATCH_DS", source)

    def test_go_worker_timeout_handlers_are_documented_owner(self):
        readme = (GO_WORKER_ROOT / "README.md").read_text(encoding="utf-8")
        task_types = (GO_WORKER_ROOT / "tasks" / "types.go").read_text(encoding="utf-8")
        main = (GO_WORKER_ROOT / "cmd" / "worker" / "main.go").read_text(encoding="utf-8")

        self.assertIn("timeout:collect_order", readme)
        self.assertIn("TypeCollectOrderTimeout", task_types)
        self.assertIn("timeout:collect_order", task_types)
        self.assertIn("mux.HandleFunc(tasks.TypeCollectOrderTimeout", main)
        self.assertIn("mux.HandleFunc(tasks.TypePayoutClaimTimeout", main)


if __name__ == "__main__":
    unittest.main()
