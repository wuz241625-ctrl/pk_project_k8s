from datetime import datetime, time, timezone

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
    return datetime.now(timezone.utc).replace(tzinfo=None)


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


def _as_utc_aware(value=None):
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return pytz.utc.localize(value)
    return value.astimezone(pytz.utc)


def display_today_between(key="time_create", now=None):
    display_tz = display_timezone()
    display_date = _as_utc_aware(now).astimezone(display_tz).date()
    start_local = display_tz.localize(datetime.combine(display_date, time.min))
    end_local = display_tz.localize(datetime.combine(display_date, time.max.replace(microsecond=0)))
    return {
        "key": key,
        "start": start_local.astimezone(pytz.utc).replace(tzinfo=None),
        "end": end_local.astimezone(pytz.utc).replace(tzinfo=None),
    }
