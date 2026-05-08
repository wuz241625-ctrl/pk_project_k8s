from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class CrawlFrequentlyRetirementTests(unittest.TestCase):
    def test_active_backend_code_no_longer_reads_or_writes_crawl_frequently(self):
        active_roots = [
            PROJECT_ROOT / "api" / "application",
            PROJECT_ROOT / "api" / "jobs",
            PROJECT_ROOT / "admin",
            PROJECT_ROOT / "merchant",
        ]
        ignored_dirs = {"__pycache__"}
        offenders = []

        for root in active_roots:
            for path in root.rglob("*.py"):
                if not path.is_file():
                    continue
                if ignored_dirs.intersection(path.parts):
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                if "crawl_frequently_" in text:
                    offenders.append(str(path.relative_to(PROJECT_ROOT)))

        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
