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


def _base_config():
    return dict(
        tenant_code=_env("TENANT_CODE", "local"),
        redis_host=_env("REDIS_HOST", "redis"),
        mysql_host=_env("MYSQL_HOST", "mysql"),
        mysql_user=_env("MYSQL_USER", "root"),
        mysql_password=_env("MYSQL_PASSWORD", "Pass_1234"),
        mysql_database=_env("MYSQL_DATABASE", "pakistan"),
        debug=_env_bool("DEBUG", False),
        api_url=_env("ADMIN_API_URL", "http://api:9000"),
        cookie_key=_env("ADMIN_COOKIE_KEY", "change-me-admin-cookie-key"),
        id_token_key=_env("ADMIN_ID_TOKEN_KEY", "change-me-admin-id-token-key"),
        BOT_TOKEN=_env("BOT_TOKEN", ""),
        SQL_TIMEOUT=_env_int("SQL_TIMEOUT", 3000),
        GROUP_ID=_env_int("GROUP_ID", 0),
        robotApi=_env("ADMIN_ROBOT_API", "https://robot.example.com"),
    )


dev = _base_config()

product = _base_config()


def get_config():
    env = os.environ.get("RUN_ENV", "DEV")
    if env == "DEV":
        return dict(dev)
    return dict(product)
