"""Slice 6: removal endpoint integration tests (fake adapters, no network)."""

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
            findings=[ToolFinding(type="email_exposure", title="found on github",
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


def _make_and_run(client, monkeypatch, url="https://github.com/alice/profile"):
    import tools.registry as treg
    from tools.base import ToolFinding, ToolResult

    class _DynamicEmailAdapter:
        name = "fakemail"
        target_types = ("email",)

        def run(self, target):
            return ToolResult(
                tool=self.name, status="completed",
                findings=[ToolFinding(type="email_exposure", title="found",
                                      source="leakdb", url=url, evidence="synthetic",
                                      confidence="confirmed", severity="high")],
                coverage={"sources_total": 1, "sources_checked": 1, "sources_failed": 0},
            )

    monkeypatch.setattr(treg, "build_registry",
                        lambda **kw: [_DynamicEmailAdapter(), FakeSearchAdapter()])
    r = client.post("/api/scans", json={"targetType": "email", "targetValue": "a@example.com"})
    assert r.status_code == 201
    scan_id = r.json()["id"]
    run = client.post(f"/api/scans/{scan_id}/run")
    assert run.status_code == 200 and run.json()["status"] == "completed"
    client.post(f"/api/scans/{scan_id}/deletion-research")
    findings = client.get(f"/api/scans/{scan_id}/findings").json()["data"]
    return scan_id, findings[0]


def test_per_finding_remove_login_gated_requires_manual(client, monkeypatch):
    _scan_id, finding = _make_and_run(client, monkeypatch,
                                      url="https://github.com/alice/profile")
    assert finding["status"] == "open"
    body = client.post(f"/api/findings/{finding['id']}/remove")
    assert body.status_code == 200
    result = body.json()
    assert result["findingId"] == finding["id"]
    assert result["status"] == "pending"
    assert result["execution"]["status"] == "requires_manual"
    assert result["execution"]["channel"] == "account_delete"
    assert "github.com" in result["execution"]["targetUrl"]


def test_finding_detail_exposes_action_id(client, monkeypatch):
    _scan_id, finding = _make_and_run(client, monkeypatch,
                                      url="https://github.com/alice/profile")
    detail = client.get(f"/api/findings/{finding['id']}").json()
    assert detail["actionId"] is not None


def test_actions_serialize_execution_summary(client, monkeypatch):
    _scan_id, finding = _make_and_run(client, monkeypatch,
                                      url="https://spokeo.com/u/alice")
    body = client.post(f"/api/findings/{finding['id']}/remove").json()
    assert body["execution"]["status"] == "requires_manual"
    assert body["execution"]["channel"] == "anonymous_form"

    action = client.get(f"/api/findings/{finding['id']}").json()
    row = client.get(f"/api/actions/{action['actionId']}").json()
    assert row["execution"]["status"] == "requires_manual"
    assert row["execution"]["targetUrl"]
    assert row["siteAdvisory"]["category"] == "data-broker"


def test_remove_missing_finding_404(client):
    assert client.post("/api/findings/99999/remove").status_code == 404


def test_remove_after_decline_409(client, monkeypatch):
    _scan_id, finding = _make_and_run(client, monkeypatch)
    action = client.get(f"/api/findings/{finding['id']}").json()["actionId"]
    assert client.post(f"/api/actions/{action}/decline").status_code == 200
    assert client.post(f"/api/findings/{finding['id']}/remove").status_code == 409