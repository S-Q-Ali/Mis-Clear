"""SSRF / unsafe-URL guardrails (Phase 13, master plan Phase 13).

Used wherever a URL is derived from a target, a user-editable manifest, or
untrusted evidence before the backend fetches it. All helpers are pure and
dependency-free (stdlib `ipaddress`/`urllib`).

Design rule: these checks prove the request target is a public web URL; they
are NOT a substitute for treating response bodies as untrusted data.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

_ALLOWED_SCHEMES = ("http", "https")

# Hostname families that resolve to this machine or link-local networks.
_PRIVATE_HOSTNAMES = re.compile(
    r"^(localhost|localhost\.localdomain|metadata\.google\.internal|"
    r"instance-data(\..+)?|169\.254\.169\.254)$",
    re.IGNORECASE,
)
_PRIVATE_SUFFIXES = (".local", ".localhost", ".internal", ".home.arpa", ".localdomain")


def _host_is_private_ip(host: str) -> bool:
    """True when `host` is an IP literal that is not a public unicast address."""
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    if addr.is_multicast or addr.is_reserved or addr.is_unspecified:
        return True
    if addr.version == 4 and addr.is_private:
        return True
    return bool(addr.is_loopback or addr.is_link_local)


def _host_is_private_name(host: str) -> bool:
    if _PRIVATE_HOSTNAMES.match(host):
        return True
    lowered = host.lower()
    return any(lowered.endswith(sfx) for sfx in _PRIVATE_SUFFIXES)


def unsafe_url_reason(url: str) -> str | None:
    """Return a human reason when `url` must not be fetched, else None."""
    if not url:
        return "empty URL"
    parsed = urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        return f"scheme not allowed: {parsed.scheme or 'none'!r}"
    host = parsed.hostname
    if not host:
        return "no hostname"
    if "@" in parsed.netloc:
        return "userinfo not allowed"
    if _host_is_private_ip(host):
        return f"private/reserved host: {host}"
    if _host_is_private_name(host):
        return f"private hostname family: {host}"
    return None


def assert_safe_web_url(url: str) -> None:
    """Raise ValueError unless `url` is a safe public http(s) URL."""
    reason = unsafe_url_reason(url)
    if reason:
        raise ValueError(f"unsafe URL ({reason}): {url!r}")


def probe_url_safe(probe: str) -> str | None:
    """Validate a sitecheck manifest probe URL (host may carry `{target}`).

    Returns None when safe, or a reason string otherwise. Key rule: the
    `{target}` placeholder may appear in the path/query but never inside the
    scheme://authority — otherwise a target like ``169.254.169.254`` or
    ``evil.example`` could redirect the laptop's fetch to an internal service.
    """
    parsed = urlparse(probe)
    if parsed.scheme.lower() != "https":
        return "manifest probe URL must be https"
    authority = parsed.netloc
    if "{" in authority or "}" in authority:
        return "target placeholder must not appear in the authority"
    host = parsed.hostname
    if not host:
        return "probe URL has no hostname"
    if _host_is_private_ip(host):
        return f"probe URL points at a private/reserved host: {host}"
    if _host_is_private_name(host):
        return f"probe URL hostname is private: {host}"
    return None


def formatted_url_matches(url: str, base: str) -> bool:
    """True when an interpolated URL keeps the manifest's scheme + host."""
    try:
        a = urlparse(url)
        b = urlparse(base.format(target=""))
    except (ValueError, KeyError):
        return False
    return (
        a.scheme.lower() == b.scheme.lower()
        and (a.hostname or "").lower() == (b.hostname or "").lower()
        and a.username is None
    )