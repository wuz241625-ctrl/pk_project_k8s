import os


def _enabled(name: str, default: str = "1") -> bool:
    value = os.environ.get(name, default)
    return str(value).strip().lower() not in {"0", "false", "off", "no"}


def runtime_read_enabled() -> bool:
    return _enabled("JAZZCASH_RUNTIME_READ_ENABLED")


def runtime_write_enabled() -> bool:
    return _enabled("JAZZCASH_RUNTIME_WRITE_ENABLED")
