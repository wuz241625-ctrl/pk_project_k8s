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

    def test_easypaisa_processes_do_not_raw_read_or_write_legacy_bridge_projection(self):
        repo_root = Path(__file__).resolve().parents[2]
        watched_files = [
            Path("api/jobs/easypaisa/auto_payout.py"),
            Path("api/jobs/easypaisa/easypaisa_monitor.py"),
        ]
        forbidden_fragments = [
            "payment_online_df",
            "payment_online_ds",
            "payment_active_df",
            "self.redis.lpop(self.REDIS_KEYS['easypaisa_active_df'])",
            "self.redis.lrem(self.REDIS_KEYS['easypaisa_active_df']",
            "self.redis.rpush(self.REDIS_KEYS['easypaisa_active_df']",
            "self.redis.srem('payment_online_df'",
            "self.redis.srem('payment_online_ds'",
            "self.redis.lrem('payment_active_df'",
            "self.redis.lrem(f'payment_active_",
            "self.redis.delete(f'kick_off_",
        ]
        offenders = []

        for rel in watched_files:
            text = (repo_root / rel).read_text(encoding="utf-8", errors="ignore")
            for fragment in forbidden_fragments:
                if fragment in text:
                    offenders.append(f"{rel}: {fragment}")

        partner_text = (repo_root / "admin/application/partner/partner.py").read_text(
            encoding="utf-8",
            errors="ignore",
        )
        reset_section = partner_text.split("class resettingPayment", 1)[1].split(
            "class batchDisablePayment",
            1,
        )[0]
        for fragment in forbidden_fragments:
            if fragment in reset_section:
                offenders.append(f"admin/application/partner/partner.py#resettingPayment: {fragment}")

        self.assertEqual(
            offenders,
            [],
            "EasyPaisa 进程不能直接读写 legacy bridge 投影；必须经 runtime service/legacy bridge。",
        )


if __name__ == "__main__":
    unittest.main()
