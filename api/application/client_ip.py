from ipaddress import ip_address


def _header_get(headers, name):
    if not headers:
        return None
    value = headers.get(name)
    if value is None:
        value = headers.get(name.lower())
    return value


def _clean_ip(value):
    if not value:
        return None
    value = str(value).strip()
    if not value or value.lower() == "unknown":
        return None
    if value.startswith("[") and "]" in value:
        value = value[1:value.index("]")]
    if value.count(":") == 1:
        host, port = value.rsplit(":", 1)
        if port.isdigit():
            value = host
    try:
        return str(ip_address(value))
    except ValueError:
        return None


def _is_trusted_proxy(value):
    cleaned = _clean_ip(value)
    if not cleaned:
        return False
    try:
        ip = ip_address(cleaned)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


def _candidate_ips(headers):
    forwarded_for = _header_get(headers, "X-Forwarded-For")
    if forwarded_for:
        for part in str(forwarded_for).split(","):
            cleaned = _clean_ip(part)
            if cleaned:
                yield cleaned

    for header_name in ("X-Real-IP", "X-Real-Ip"):
        cleaned = _clean_ip(_header_get(headers, header_name))
        if cleaned:
            yield cleaned


def resolve_client_ip(headers, remote_ip):
    remote = _clean_ip(remote_ip) or str(remote_ip or "")
    if not _is_trusted_proxy(remote):
        return remote

    candidates = list(_candidate_ips(headers))
    for candidate in candidates:
        try:
            if ip_address(candidate).is_global:
                return candidate
        except ValueError:
            continue

    if candidates:
        return candidates[0]
    return remote
