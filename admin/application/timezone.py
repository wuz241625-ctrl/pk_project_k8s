from datetime import datetime, timezone

import pytz

try:
    from config import get_config
except ImportError:
    get_config = None


conf = get_config() if get_config else {}


def _conf_value(name, default):
    if isinstance(conf, dict):
        return conf.get(name, default)
    return getattr(conf, name, default)


def get_business_timezone_name():
    return _conf_value("business_timezone", "UTC")


def get_display_timezone_name():
    return _conf_value("display_timezone", "Asia/Karachi")


def business_now_utc():
    return datetime.utcnow()


def display_timezone():
    return pytz.timezone(get_display_timezone_name())


def display_now():
    return datetime.now(display_timezone())


def format_for_display(value=None, fmt="%Y-%m-%d %H:%M:%S"):
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = pytz.utc.localize(value)
    return value.astimezone(display_timezone()).strftime(fmt)


def display_to_utc_naive(value, fmt="%Y-%m-%d %H:%M:%S"):
    if isinstance(value, str):
        value = datetime.strptime(value, fmt)
    if value.tzinfo is None:
        value = display_timezone().localize(value)
    return value.astimezone(pytz.utc).replace(tzinfo=None)
