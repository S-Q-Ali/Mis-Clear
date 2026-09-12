"""Phase 11: deletion research API integration tests (fake adapters, no network)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from tools.base import ToolFinding, ToolResult


class FakeEmailAdapter:
    name = "fakemail"
    target_types = ("email",)

    def run(self, target: str) -> ToolResult:
        return ToolResult(
            tool=self.name, status="completed",
            findings=[ToolFinding(type="email_exposure", title="found on leakdb",
                                  source="leakdb", url="https://github.com/alice/profile",
                                  evidence="synthetic", confidence="confirmed",
                                  severity="high")],
            coverage={"sources_total": 1, "sources_checked": 1, "sources_failed": 0},
        )


class FakeSearchAdapter:
    name = "fakesearch"
    target_types = ("email", "username", "custom")

    def run(self, target: str) -> ToolResult:
        return ToolResult(tool=self.name, status="completed",
                          coverage={"sources_total": 2, "sources_checked": 2, "sources_failed": 0})


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import app.backend.api.workers as wk
    import app.backend.config as cfg
    import app.backend.database.engine as eng
    import app.backend.services.job_dispatcher as jd

    test_settings = cfg.Settings(
        database_path=str(tmp_path / "api.db"), ollama_url="", colab_ollama_url=""
    )
    monkeypatch.setattr(cfg, "settings", test_settings)
    monkeypatch.setattr(eng, "settings", test_settings)
    monkeypatch.setattr(wk, "settings", test_settings)
    monkeypatch.setattr(jd, "settings", test_settings)

    eng.engine = eng.build_engine(test_settings.database_path)
    eng.SessionLocal = sessionmaker(bind=eng.engine, autoflush=False, autocommit=False)
    eng.init_db()

    from app.backend.main import create_app

    with TestClient(create_app()) as c:
        yield c


def _make_and_run(client, target, monkeypatch):
    import tools.registry as treg

    monkeypatch.setattr(treg, "build_registry",
                        lambda **kw: [FakeEmailAdapter(), FakeSearchAdapter()])
    r = client.post("/api/scans", json={"targetType": "email", "targetValue": target})
    assert r.status_code == 201
    scan_id = r.json()["id"]
    run = client.post(f"/api/scans/{scan_id}/run")
    assert run.status_code == 200 and run.json()["status"] == "completed"
    return scan_id


def test_deletion_research_creates_approved_action_flow(client, monkeypatch):
    scan_id = _make_and_run(client, "alice@example.com", monkeypatch)
    body = client.post(f"/api/scans/{scan_id}/deletion-research").json()
    assert body["scanId"] == scan_id
    assert body["created"] == 1

    actions = client.get("/api/actions", params={"scanId": scan_id}).json()
    row = actions["data"][0]
    action_id = row["id"]
    assert row["approvalRequired"] is True
    assert row["status"] == "pending"
    assert "GitHub, Inc." in row["instructions"]

    approve = client.post(f"/api/actions/{action_id}/approve")
    assert approve.status_code == 200 and approve.json()["status"] == "approved"
    detail = client.get(f"/api/actions/{action_id}").json()
    assert detail["status"] == "approved"


def test_deletion_research_idempotent_and_audit(client, monkeypatch):
    scan_id = _make_and_run(client, "bob@example.com", monkeypatch)
    c1 = client.post(f"/api/scans/{scan_id}/deletion-research").json()
    assert c1["created"] == 1 and c1["skipped"] == 0
    c2 = client.post(f"/api/scans/{scan_id}/deletion-research").json()
    assert c2["created"] == 0 and c2["skipped"] == 1

    actions = client.get("/api/actions", params={"scanId": scan_id}).json()
    assert actions["pagination"]["totalItems"] == 1


def test_decline_flow_and_non_pending_409(client, monkeypatch):
    scan_id = _make_and_run(client, "carol@example.com", monkeypatch)
    client.post(f"/api/scans/{scan_id}/deletion-research")
    actions = client.get("/api/actions", params={"scanId": scan_id}).json()
    action_id = actions["data"][0]["id"]

    assert client.post(f"/api/actions/{action_id}/decline").json()["status"] == "declined"
    assert client.post(f"/api/actions/{action_id}/approve").status_code == 409
    assert client.post(f"/api/actions/{action_id}/decline").json()["status"] == "declined"


def test_research_missing_scan_and_action_404(client):
    assert client.post("/api/scans/99999/deletion-research").status_code == 404
    assert client.get("/api/actions/99999").status_code == 404
    assert client.post("/api/actions/99999/approve").status_code == 404
    assert client.post("/api/actions/99999/decline").status_code == 404


def test_actions_list_filter_by_status(client, monkeypatch):
    scan_id = _make_and_run(client, "dan@example.com", monkeypatch)
    client.post(f"/api/scans/{scan_id}/deletion-research")
    actions = client.get("/api/actions", params={"status": "pending"}).json()
    assert actions["pagination"]["totalItems"] >= 1
    assert all(a["status"] == "pending" for a in actions["data"])