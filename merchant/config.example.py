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
        tenant_code=_env("TENANT_CODE", "d7pay"),
        redis_host=_env("REDIS_HOST", "redis"),
        mysql_host=_env("MYSQL_HOST", "mysql"),
        mysql_user=_env("MYSQL_USER", "d7pay_app"),
        mysql_password=_env("MYSQL_PASSWORD", "8e8PRyJD0CPJmjNeKZMpTJBP__bEKSLQteO_miYo"),
        mysql_database=_env("MYSQL_DATABASE", "pakistan_d7pay"),
        debug=_env_bool("DEBUG", False),
        api_url=_env("MERCHANT_API_URL", "http://api:9000"),
        cookie_key=_env("MERCHANT_COOKIE_KEY", "kL9cSqoXXkKCF8vmd8J1-lDem3VmfBogfRaPXhLVSMc8sDN1x7DECWNhKcvncENp"),
    )


def get_config():
    return _base_config()
