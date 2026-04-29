import os


def _env(name, default):
    return os.environ.get(name, default)


def _env_bool(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _base_config():
    return dict(
        tenant_code=_env("TENANT_CODE", "local"),
        redis_host=_env("REDIS_HOST", "redis"),
        mysql_host=_env("MYSQL_HOST", "mysql"),
        mysql_user=_env("MYSQL_USER", "root"),
        mysql_password=_env("MYSQL_PASSWORD", "Pass_1234"),
        mysql_database=_env("MYSQL_DATABASE", "pakistan"),
        debug=_env_bool("DEBUG", False),
        api_url=_env("MERCHANT_API_URL", "http://api:9000"),
        cookie_key=_env("MERCHANT_COOKIE_KEY", "change-me-merchant-cookie-key"),
    )


dev = _base_config()

product = _base_config()


def get_config():
    env = os.environ.get("RUN_ENV", "DEV")
    if env == "DEV":
        return dict(dev)
    return dict(product)
