from urllib.parse import urlsplit


def _host_of(lower):
    host = lower
    split = urlsplit(lower)
    if split.scheme:
        host = split.netloc or split.path
        # strip userinfo and port
        if "@" in host:
            host = host.rsplit("@", 1)[1]
        if ":" in host and not host.startswith("["):
            host = host.split(":", 1)[0]
    return host


def matched_by(url_or_host, domains_set, custom_keywords):
    """Return the keyword or domain that matched, else None.

    - custom_keywords: substring match on the whole string (case-insensitive)
    - domains_set: exact or sub-domain suffix match against the host part
    """
    lower = url_or_host.lower()

    for kw in custom_keywords:
        if kw and kw in lower:
            return kw

    if not domains_set:
        return None

    host = _host_of(lower)
    labels = host.split(".")
    for i in range(len(labels)):
        candidate = ".".join(labels[i:])
        if candidate in domains_set:
            return candidate
    return None


def matches(url_or_host, domains_set, custom_keywords):
    """Return True if url_or_host matches a custom keyword OR any blocked domain."""
    return matched_by(url_or_host, domains_set, custom_keywords) is not None