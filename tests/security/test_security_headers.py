"""Security response headers (Phase 13)."""

from app.backend.main import create_app
from app.backend.security.middleware import (
    CSP,
    FRAME_OPTIONS,
    NO_STORE,
    REFERRER,
    X_CONTENT_TYPE,
)


def test_security_headers_present_on_api_responses(client):
    r = client.get("/api/settings")
    assert r.status_code == 200
    h = {k.lower(): v for k, v in r.headers.items()}
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert h["referrer-policy"] == "no-referrer"
    assert h["content-security-policy"] == "default-src 'none'"
    assert h["cache-control"] == "no-store"


def test_api_responses_cached_no_store_elsewhere(client):
    h = {k.lower(): v for k, v in client.get("/health").headers.items()}
    assert "cache-control" not in h


def test_headers_constant_exports():
    assert X_CONTENT_TYPE == "nosniff"
    assert FRAME_OPTIONS == "DENY"
    assert REFERRER == "no-referrer"
    assert CSP == "default-src 'none'"
    assert NO_STORE


def test_headers_applied_via_middleware():
    app = create_app()
    names = {getattr(m, "cls", m).__name__ for m in app.user_middleware}
    assert "SecurityHeadersMiddleware" in names, "middleware not registered"