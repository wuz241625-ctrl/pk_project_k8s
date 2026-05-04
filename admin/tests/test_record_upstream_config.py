import importlib.util
import os
import unittest
from pathlib import Path


class AdminRecordUpstreamConfigTests(unittest.TestCase):
    def test_conf_get_reads_dict_config(self):
        from application.record.upstream_config import conf_get

        self.assertEqual(
            conf_get({"easypaisa_api_url": "http://new-upstream"}, "easypaisa_api_url", "old"),
            "http://new-upstream",
        )

    def test_conf_get_reads_object_config(self):
        from application.record.upstream_config import conf_get

        class Config:
            jazzcash_user_id = "new-user"

        self.assertEqual(conf_get(Config(), "jazzcash_user_id", "old"), "new-user")

    def test_admin_config_example_exposes_upstream_env(self):
        config_path = Path(__file__).resolve().parents[1] / "config.example.py"
        spec = importlib.util.spec_from_file_location("admin_config_example_under_test", config_path)
        module = importlib.util.module_from_spec(spec)

        env_values = {
            "EASYPAISA_API_URL": "http://ep-upstream",
            "EASYPAISA_USER_ID": "ep-user",
            "EASYPAISA_SECRET_KEY": "ep-secret",
            "JAZZCASH_API_URL": "http://jc-upstream",
            "JAZZCASH_USER_ID": "jc-user",
            "JAZZCASH_SECRET_KEY": "jc-secret",
        }
        old_values = {key: os.environ.get(key) for key in env_values}
        try:
            os.environ.update(env_values)
            spec.loader.exec_module(module)
            conf = module.get_config()
        finally:
            for key, value in old_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        for key, value in {
            "easypaisa_api_url": "http://ep-upstream",
            "easypaisa_user_id": "ep-user",
            "easypaisa_secret_key": "ep-secret",
            "jazzcash_api_url": "http://jc-upstream",
            "jazzcash_user_id": "jc-user",
            "jazzcash_secret_key": "jc-secret",
        }.items():
            self.assertEqual(conf[key], value)


if __name__ == "__main__":
    unittest.main()
