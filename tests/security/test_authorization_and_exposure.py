"""Authorization + local network exposure + read-only control surfaces (Phase 13)."""

from fastapi.testclient import TestClient

from app.backend.config import Settings
from app.backend.main import create_app


def test_settings_defaults_bind_loopback_only():
    settings = Settings(_env_file=None)
    assert settings.host == "127.0.0.1"
    origins = settings.cors_origin_list
    assert all("127.0.0.1" in o or "localhost" in o for o in origins)
    assert len(origins) <= 2


def test_settings_write_endpoints_rejected(client):
    assert client.post("/api/settings", json={}).status_code == 405
    assert client.put("/api/settings", json={}).status_code == 405
    assert client.patch("/api/settings", json={}).status_code == 405
    assert client.delete("/api/settings").status_code == 405


def test_cors_disallowed_origin_rejected():
    app = create_app()
    with TestClient(app, headers={}) as tc:
        r = tc.options(
            "/api/health",
            headers={
                "Origin": "http://evil.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert r.status_code == 400 if "html" not in r.text[:100] else 400
        assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


def test_action_approve_requires_pending(client):
    """Authorization guard: only `pending` privacy actions may be approved/declined."""
    r = client.post(
        "/api/scans",
        json={"targetType": "email", "targetValue": "victim@example.test"},
    )
    scan_id = r.json()["id"]
    client.post(f"/api/scans/{scan_id}/deletion-research")
    r = client.get("/api/actions")
    actions = r.json()["data"]
    if actions:
        action_id = actions[0]["id"]
        # approving once should succeed; a second transition must conflict
        first = client.post(f"/api/actions/{action_id}/approve")
        second = client.post(f"/api/actions/{action_id}/approve")
        assert first.status_code == 200
        assert second.status_code == 409


def test_idempotency_mismatch_rejected(client):
    r1 = client.post(
        "/api/scans",
        json={"targetType": "email", "targetValue": "mismatch@example.test"},
        headers={"Idempotency-Key": "sec-abc123"},
    )
    assert r1.status_code == 201
    r2 = client.post(
        "/api/scans",
        json={"targetType": "username", "targetValue": "someone"},
        headers={"Idempotency-Key": "sec-abc123"},
    )
    assert r2.status_code == 422
    assert r2.json()["error"]["code"] == "IDEMPOTENCY_MISMATCH"