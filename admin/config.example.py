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
        tenant_code=_env("TENANT_CODE", "d7pay"),
        redis_host=_env("REDIS_HOST", "redis"),
        mysql_host=_env("MYSQL_HOST", "mysql"),
        mysql_user=_env("MYSQL_USER", "d7pay_app"),
        mysql_password=_env("MYSQL_PASSWORD", "8e8PRyJD0CPJmjNeKZMpTJBP__bEKSLQteO_miYo"),
        mysql_database=_env("MYSQL_DATABASE", "pakistan_d7pay"),
        debug=_env_bool("DEBUG", False),
        api_url=_env("ADMIN_API_URL", "http://api:9000"),
        cookie_key=_env("ADMIN_COOKIE_KEY", "0hcZJEjUBe0p0RZJpwAJj7sYggzgwR0Gft6_KdxooLq5B7FPgkvIbbr31mug6f4R"),
        id_token_key=_env("ADMIN_ID_TOKEN_KEY", "W1J7ODU74RhZ4thGvp7jludnpDJ0z4tE4-CMsq6E9DAwzIL1ZJP6DwIDawhDjkvS"),
        BOT_TOKEN=_env("BOT_TOKEN", ""),
        SQL_TIMEOUT=_env_int("SQL_TIMEOUT", 3000),
        GROUP_ID=_env_int("GROUP_ID", 0),
        robotApi=_env("ADMIN_ROBOT_API", "https://robot.example.com"),
        easypaisa_api_url=_env("EASYPAISA_API_URL", "http://34.150.42.92:83"),
        easypaisa_user_id=_env("EASYPAISA_USER_ID", "177651e475bc439cac98d4b54ce4f6b1"),
        easypaisa_secret_key=_env("EASYPAISA_SECRET_KEY", "39eafd9c3767471e9d0fae1906dd706e"),
        jazzcash_api_url=_env("JAZZCASH_API_URL", "http://34.150.42.92:84"),
        jazzcash_user_id=_env("JAZZCASH_USER_ID", "ba08c3c0e4f546ad92dd2c2e8542ca36"),
        jazzcash_secret_key=_env("JAZZCASH_SECRET_KEY", "ca45b35e132b46b9b68dd55f1ab077de"),
    )


def get_config():
    return _base_config()
