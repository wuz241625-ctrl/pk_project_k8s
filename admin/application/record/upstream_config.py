def conf_get(conf, key, default=None):
    if isinstance(conf, dict):
        return conf.get(key, default)
    return getattr(conf, key, default)
