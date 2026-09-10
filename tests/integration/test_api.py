"""Phase 5 API integration tests. Isolated temp SQLite + monkeypatched settings."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.backend import models as m


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import app.backend.config as cfg
    import app.backend.database.engine as eng
    import app.backend.api.workers as wk

    test_settings = cfg.Settings(
        database_path=str(tmp_path / "api.db"), ollama_url="", colab_ollama_url=""
    )
    monkeypatch.setattr(cfg, "settings", test_settings)
    monkeypatch.setattr(eng, "settings", test_settings)
    monkeypatch.setattr(wk, "settings", test_settings)

    eng.engine = eng.build_engine(test_settings.database_path)
    eng.SessionLocal = sessionmaker(bind=eng.engine, autoflush=False, autocommit=False)
    eng.init_db()

    from app.backend.main import create_app

    with TestClient(create_app()) as c:
        yield c


def db_session():
    import app.backend.database.engine as eng

    return eng.SessionLocal()


def test_create_get_list_scan(client):
    r = client.post("/api/scans", json={"targetType": "email", "targetValue": "alice@example.com", "scanMode": "local"})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "pending"
    assert body["targetValue"] == "alice@example.com"

    g = client.get(f"/api/scans/{body['id']}")
    assert g.status_code == 200 and g.json()["id"] == body["id"]

    lst = client.get("/api/scans")
    assert lst.status_code == 200
    assert lst.json()["pagination"]["totalItems"] == 1
    assert len(lst.json()["data"]) == 1


def test_create_scan_validation_error(client):
    r = client.post("/api/scans", json={"targetType": "email", "targetValue": "not-an-email", "scanMode": "local"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_scan_not_found(client):
    r = client.get("/api/scans/9999")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize("status", [200, 404])
def test_findings_fixture(client, tmp_path, status):
    r = client.post("/api/scans", json={"targetType": "username", "targetValue": "alice_88"})
    assert r.status_code == 201
    scan_id = r.json()["id"]

    # insert findings directly (API layer is read-only for findings)
    with db_session() as db:
        db.add(m.Finding(scan_id=scan_id, type="username_profile", title="Profile found",
                         source="synthetic", url="https://example.test/u/alice_88",
                         evidence="synthetic fixture", confidence="possible", severity="medium",
                         tool="fixture"))
        db.commit()

    if status == 200:
        f = client.get(f"/api/scans/{scan_id}/findings")
        assert f.status_code == 200
        assert f.json()["pagination"]["totalItems"] == 1
        assert f.json()["data"][0]["tool"] == "fixture"
    else:
        r2 = client.get("/api/scans/7777/findings")
        assert r2.status_code == 404


def test_job_create_get(client):
    r = client.post("/api/jobs", json={
        "jobId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "jobType": "vision_analysis",
        "payload": {"n": 2}, "requestedCapabilities": ["vision"]})
    assert r.status_code == 201
    assert r.json()["status"] == "queued"

    dup = client.post("/api/jobs", json={
        "jobId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "jobType": "vision_analysis",
        "payload": {"n": 2}})
    assert dup.status_code == 201  # idempotent replay same definition

    conflict = client.post("/api/jobs", json={
        "jobId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "jobType": "vision_analysis",
        "payload": {"n": 99}})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "JOB_CONFLICT"

    g = client.get("/api/jobs")
    assert g.status_code == 200 and g.json()["pagination"]["totalItems"] == 1


def test_worker_status_honest(client):
    w = client.get("/api/workers")
    assert w.status_code == 200
    body = w.json()
    assert body["localAiConfigured"] is False  # no ollama configured in test
    assert body["colabAiConfigured"] is False
    assert body["colabAiAvailable"] is False


def test_report_aggregates(client, tmp_path):
    r = client.post("/api/scans", json={"targetType": "custom", "targetValue": "handle"})
    scan_id = r.json()["id"]
    with db_session() as db:
        db.add(m.Finding(scan_id=scan_id, type="email_exposure", title="a", source="s1",
                         confidence="confirmed", severity="high", tool="t1"))
        db.add(m.Finding(scan_id=scan_id, type="email_exposure", title="b", source="s1",
                         confidence="possible", severity="low", tool="t2"))
        db.add(m.ToolRun(scan_id=scan_id, tool="t1", status="completed", findings_count=1))
        db.commit()
    rep = client.get(f"/api/reports/{scan_id}")
    assert rep.status_code == 200
    body = rep.json()
    assert body["totalFindings"] == 2
    assert body["bySeverity"] == {"high": 1, "low": 1}
    assert body["byConfidence"] == {"confirmed": 1, "possible": 1}
    assert "t1" in body["sourcesChecked"]
    assert body["aiAvailable"] is False


def test_idempotency_replay(client):
    body = {"targetType": "email", "targetValue": "bob@example.com", "scanMode": "local"}
    first = client.post("/api/scans", json=body, headers={"Idempotency-Key": "key-1"})
    assert first.status_code == 201
    second = client.post("/api/scans", json=body, headers={"Idempotency-Key": "key-1"})
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]


def test_idempotency_mismatch_rejected(client):
    body_a = {"targetType": "email", "targetValue": "bob@example.com", "scanMode": "local"}
    body_b = {"targetType": "email", "targetValue": "carol@example.com", "scanMode": "local"}
    client.post("/api/scans", json=body_a, headers={"Idempotency-Key": "key-2"})
    r = client.post("/api/scans", json=body_b, headers={"Idempotency-Key": "key-2"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "IDEMPOTENCY_MISMATCH"