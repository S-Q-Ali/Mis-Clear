"""Phase 14 E2E: security headers over real HTTP, health, and a server restart.

The restart test proves the "system of record" property: data lives in the DB,
so a fresh process boot finds scans/findings intact, and re-running after
restart stays consistent.
"""

from __future__ import annotations

import httpx


def test_security_headers_present_over_http(http):
    client, _ = http
    resp = client.get("/api/settings")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "no-referrer"
    assert "default-src 'none'" in resp.headers["content-security-policy"]
    assert "no-store" in resp.headers.get("cache-control", "")


def test_health_and_readonly_settings_over_http(http):
    client, _ = http
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    settings = client.get("/api/settings").json()
    assert settings["readOnly"] is True
    assert settings["localAiConfigured"] is False


def test_server_restart_preserves_data_and_allows_rerun(http, e2e_settings):
    client, manager = http

    r = client.post("/api/scans", json={"targetType": "email", "targetValue": "restart@example.com"})
    scan_id = r.json()["id"]
    run = client.post(f"/api/scans/{scan_id}/run")
    assert run.json()["status"] == "completed"

    manager.stop()
    manager.start()

    with httpx.Client(base_url=manager.base_url, timeout=30) as client2:
        scan = client2.get(f"/api/scans/{scan_id}").json()
        assert scan["id"] == scan_id
        assert scan["status"] == "completed"
        assert scan["targetValue"] == "restart@example.com"

        findings = client2.get(f"/api/scans/{scan_id}/findings").json()
        assert findings["pagination"]["totalItems"] == 1

        rerun = client2.post(f"/api/scans/{scan_id}/run")
        assert rerun.status_code == 200
        assert rerun.json()["status"] == "completed"

        lists = client2.get("/api/scans").json()
        assert lists["pagination"]["totalItems"] >= 1