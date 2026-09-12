"""SSRF / unsafe-URL guardrail tests (Phase 13)."""

import pytest

from app.backend.security.url_safety import (
    assert_safe_web_url,
    formatted_url_matches,
    probe_url_safe,
)

SAFE = [
    "https://example.com/u/123",
    "http://example.test/members/check",
    "https://api.github.com/users/octocat",
]

UNSAFE_SCHEMES = ["file:///etc/passwd", "javascript:alert(1)", "ftp://example.com/x", "data:text/plain,x"]

PRIVATE_HOSTS = [
    "http://127.0.0.1/",
    "http://169.254.169.254/latest/meta-data/",
    "http://192.168.1.1/admin",
    "http://10.0.0.5/",
    "http://172.16.0.1/x",
    "http://0.0.0.0/",
    "http://[::1]/",
    "http://[fe80::1]/x",
    "http://localhost/x",
    "http://localhost.localdomain/x",
]


@pytest.mark.parametrize("url", SAFE)
def test_accepts_public_web_urls(url):
    assert assert_safe_web_url(url) is None


@pytest.mark.parametrize("url", UNSAFE_SCHEMES + PRIVATE_HOSTS)
def test_rejects_unsafe_or_private_urls(url):
    with pytest.raises(ValueError):
        assert_safe_web_url(url)


def test_rejects_userinfo():
    with pytest.raises(ValueError):
        assert_safe_web_url("https://user:pass@evil.example/x")


def test_rejects_private_ip_hostnames():
    assert assert_safe_web_url("https://ns1.internal.example/") is None  # public-looking TLD
    with pytest.raises(ValueError):
        assert_safe_web_url("https://dev.local/")
    with pytest.raises(ValueError):
        assert_safe_web_url("https://cluster.internal/")
    with pytest.raises(ValueError):
        assert_safe_web_url("https://metadata.google.internal/")


def test_probe_url_rejects_target_in_authority():
    reason = probe_url_safe("https://{target}/login")
    assert reason is not None
    assert "authority" in reason


def test_probe_url_rejects_non_https():
    assert probe_url_safe("http://example.test/login") is not None


def test_probe_url_rejects_private_host():
    assert probe_url_safe("https://192.168.1.5/login") is not None


def test_probe_url_accepts_public_placeholder_in_path():
    assert probe_url_safe("https://example.com/u/{target}") is None


def test_formatted_url_stays_on_manifest_host():
    base = "https://example.com/u/{target}"
    assert formatted_url_matches("https://example.com/u/jane", base) is True
    assert formatted_url_matches("https://evil.example/inject", base) is False
    assert formatted_url_matches("https://169.254.169.254/x", base) is False
    assert formatted_url_matches("file:///etc/passwd", base) is False


def test_formatted_url_allows_path_controls():
    base = "https://example.com/u/{target}"
    assert formatted_url_matches("https://example.com/u/a?b=c#d", base) is True
    assert formatted_url_matches("https://example.com/oops", base) is True
    with pytest.raises(ValueError):
        assert_safe_web_url("https://user@example.com/u/x")


def test_host_placeholder_probe_url_is_caught_at_validate():
    assert probe_url_safe("https://accounts.google.com/{target}") is None
    assert probe_url_safe("https://{target}.example.com/") is not None