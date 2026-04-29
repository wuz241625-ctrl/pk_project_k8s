import os


def _env(name, default):
    return os.environ.get(name, default)


def _env_bool(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _env_int(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    return int(value)


def _env_list(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def _base_config():
    return dict(
        tenant_code=_env("TENANT_CODE", "local"),
        redis_host=_env("REDIS_HOST", "redis"),
        mysql_host=_env("MYSQL_HOST", "mysql"),
        mysql_user=_env("MYSQL_USER", "root"),
        mysql_password=_env("MYSQL_PASSWORD", "Pass_1234"),
        mysql_database=_env("MYSQL_DATABASE", "pakistan"),
        debug=_env_bool("DEBUG", False),
        autoreload=_env_bool("AUTORELOAD", False),
        pay_url=_env("API_PAY_URL", "http://api.awekay.com/api/order/"),
        ospay_api_host=_env("API_OSPAY_API_HOST", "http://api.awekay.com/api"),
        websocket_api_allow_host=_env_list(
            "API_WEBSOCKET_ALLOW_HOST",
            ["api.awekay.com"],
        ),
        key_order=_env("API_KEY_ORDER", "change-me-api-key-order"),
        secret_key=_env("API_SECRET_KEY", "change-me-api-secret-key"),
        usdt_api_endpoint=_env(
            "USDT_API_ENDPOINT",
            "https://u.dhd64971.com/api/brave_troops/usdt/remits/place_order",
        ),
        current_pay=_env("API_CURRENT_PAY", "pakistanpay"),
        BOT_TOKEN=_env("BOT_TOKEN", ""),
        SQL_TIMEOUT=_env_int("SQL_TIMEOUT", 6000),
        GROUP_ID=_env_int("GROUP_ID", 0),
        easypaisa_api_url=_env("EASYPAISA_API_URL", "http://34.150.42.92:83"),
        easypaisa_user_id=_env("EASYPAISA_USER_ID", "change-me-easypaisa-user"),
        easypaisa_secret_key=_env(
            "EASYPAISA_SECRET_KEY",
            "change-me-easypaisa-secret",
        ),
        jazzcash_api_url=_env("JAZZCASH_API_URL", "http://34.150.42.92:84"),
        jazzcash_user_id=_env("JAZZCASH_USER_ID", "change-me-jazzcash-user"),
        jazzcash_secret_key=_env(
            "JAZZCASH_SECRET_KEY",
            "change-me-jazzcash-secret",
        ),
    )


dev = _base_config()

product = _base_config()


def get_config():
    env = os.environ.get("RUN_ENV", "DEV")
    if env == "DEV":
        return dict(dev)
    return dict(product)
