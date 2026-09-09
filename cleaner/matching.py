from urllib.parse import urlsplit


def matches(url_or_host, domains_set, custom_keywords):
    """Return True if url_or_host matches a custom keyword OR any blocked domain.

    - custom_keywords: substring match on the whole string (case-insensitive)
    - domains_set: exact or sub-domain suffix match against the host part
    """
    lower = url_or_host.lower()

    for kw in custom_keywords:
        if kw and kw in lower:
            return True

    if not domains_set:
        return False

    host = lower
    split = urlsplit(lower)
    if split.scheme:
        host = split.netloc or split.path
        # strip userinfo and port
        if "@" in host:
            host = host.rsplit("@", 1)[1]
        if ":" in host and not host.startswith("["):
            host = host.split(":", 1)[0]

    labels = host.split(".")
    for i in range(len(labels)):
        candidate = ".".join(labels[i:])
        if candidate in domains_set:
            return True
    return False