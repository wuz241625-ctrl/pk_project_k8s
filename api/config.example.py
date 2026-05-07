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
        tenant_code=_env("TENANT_CODE", "d7pay"),
        redis_host=_env("REDIS_HOST", "redis"),
        mysql_host=_env("MYSQL_HOST", "mysql"),
        mysql_user=_env("MYSQL_USER", "d7pay_app"),
        mysql_password=_env("MYSQL_PASSWORD", "8e8PRyJD0CPJmjNeKZMpTJBP__bEKSLQteO_miYo"),
        mysql_database=_env("MYSQL_DATABASE", "pakistan_d7pay"),
        business_timezone=_env("BUSINESS_TIMEZONE", "UTC"),
        display_timezone=_env("APP_DISPLAY_TIMEZONE", "Asia/Karachi"),
        debug=_env_bool("DEBUG", False),
        autoreload=_env_bool("AUTORELOAD", False),
        pay_url=_env("API_PAY_URL", "https://api.d7pay.net/api/order/"),
        ospay_api_host=_env("API_OSPAY_API_HOST", "https://api.d7pay.net/api"),
        websocket_api_allow_host=_env_list(
            "API_WEBSOCKET_ALLOW_HOST",
            ["api.d7pay.net"],
        ),
        key_order=_env("API_KEY_ORDER", "6esyO1Lwe0odszwth-vda1OuXfkhWlNeT-_LuXb5f82ufvQMuq26IlM7b2p3IDFE"),
        secret_key=_env("API_SECRET_KEY", "1OYqC3-u7DkOmWrTh1zIRSdfBlI7HF4qWmvGR0ZMA_K_o58a_Hu7DGPoUmvTRArR"),
        usdt_api_endpoint=_env(
            "USDT_API_ENDPOINT",
            "https://u.dhd64971.com/api/brave_troops/usdt/remits/place_order",
        ),
        current_pay=_env("API_CURRENT_PAY", "pakistanpay"),
        BOT_TOKEN=_env("BOT_TOKEN", ""),
        SQL_TIMEOUT=_env_int("SQL_TIMEOUT", 6000),
        GROUP_ID=_env_int("GROUP_ID", 0),
        easypaisa_api_url=_env("EASYPAISA_API_URL", "http://34.150.42.92:83"),
        easypaisa_user_id=_env("EASYPAISA_USER_ID", "177651e475bc439cac98d4b54ce4f6b1"),
        easypaisa_secret_key=_env("EASYPAISA_SECRET_KEY", "39eafd9c3767471e9d0fae1906dd706e"),
        jazzcash_api_url=_env("JAZZCASH_API_URL", "http://34.150.42.92:84"),
        jazzcash_api_version=_env("JAZZCASH_API_VERSION", "v1.6"),
        jazzcash_user_id=_env("JAZZCASH_USER_ID", "ba08c3c0e4f546ad92dd2c2e8542ca36"),
        jazzcash_secret_key=_env("JAZZCASH_SECRET_KEY", "ca45b35e132b46b9b68dd55f1ab077de"),
    )


def get_config():
    return _base_config()
