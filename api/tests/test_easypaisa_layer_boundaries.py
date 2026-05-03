from pathlib import Path
import unittest


class EasyPaisaLayerBoundaryTests(unittest.TestCase):
    def test_job_projection_raw_keys_are_declared_only_in_keyspace(self):
        repo_root = Path(__file__).resolve().parents[2]
        allowed = {
            Path("api/application/easypaisa_runtime/keyspace.py"),
            Path("admin/application/easypaisa_runtime/keyspace.py"),
        }
        offenders = []

        for base in (repo_root / "api", repo_root / "admin"):
            for path in base.rglob("*.py"):
                parts = set(path.parts)
                if {"tests", "vendor", "__pycache__"} & parts:
                    continue
                rel = path.relative_to(repo_root)
                text = path.read_text(encoding="utf-8", errors="ignore")
                if "hash_easypaisa" not in text and "set_easypaisa" not in text:
                    continue
                if rel not in allowed:
                    offenders.append(str(rel))

        self.assertEqual(
            offenders,
            [],
            "hash_easypaisa/set_easypaisa 只能由 EasyPaisa runtime keyspace 声明，其他生产代码应通过 keyspace.JOB_HASH/JOB_SET 使用。",
        )


if __name__ == "__main__":
    unittest.main()
