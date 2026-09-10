"""Health endpoint must respond ok with service identity."""

from fastapi.testclient import TestClient

from app.backend.main import app

client = TestClient(app)


def test_health_ok():
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["service"] == "privacy-guardian"
    assert body["time"]


def test_health_shows_service_name_at_least_once():
    res = client.get("/health")
    assert "privacy-guardian" in res.text