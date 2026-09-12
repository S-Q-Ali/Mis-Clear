"""Phase 10: risk API integration tests (fake adapters, no network)."""

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
                                  source="leakdb", url="https://leakdb.example/data",
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


def test_risk_endpoint_computes_deterministic_scores(client, monkeypatch):
    import tools.registry as treg

    monkeypatch.setattr(treg, "build_registry",
                        lambda **kwargs: [FakeEmailAdapter(), FakeSearchAdapter()])
    r = client.post("/api/scans", json={"targetType": "email", "targetValue": "alice@example.com"})
    scan_id = r.json()["id"]
    assert client.post(f"/api/scans/{scan_id}/run").status_code == 200

    resp = client.get(f"/api/scans/{scan_id}/risk")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scanId"] == scan_id
    assert body["findingCount"] == 1
    row = body["findings"][0]
    assert row["type"] == "email_exposure"
    assert row["level"] in {"critical", "high", "medium", "low", "negligible"}
    bd = row["breakdown"]
    for k in ("severity", "confidence", "sourceReliability", "sensitivity",
              "exposureAge", "correlation"):
        assert bd[k] >= 0.0 and bd[k] <= 1.0
    assert bd["confidence"] == 1.0  # confirmed
    # reproducibility: second call identical
    assert client.get(f"/api/scans/{scan_id}/risk").json() == body


def test_risk_score_is_consistent_with_report(client, monkeypatch):
    import tools.registry as treg

    monkeypatch.setattr(treg, "build_registry",
                        lambda **kwargs: [FakeEmailAdapter(), FakeSearchAdapter()])
    r = client.post("/api/scans", json={"targetType": "email", "targetValue": "bob@example.com"})
    scan_id = r.json()["id"]
    assert client.post(f"/api/scans/{scan_id}/run").status_code == 200

    risk = client.get(f"/api/scans/{scan_id}/risk").json()
    report = client.get(f"/api/reports/{scan_id}").json()
    assert risk["findingCount"] == report["totalFindings"] == 1
    assert risk["findings"][0]["riskScore"] > 0  # confirmed/high exposure can't be negligible


def test_risk_empty_no_findings_and_404(client):
    r = client.post("/api/scans", json={"targetType": "email", "targetValue": "zoe@example.com"})
    scan_id = r.json()["id"]
    body = client.get(f"/api/scans/{scan_id}/risk").json()
    assert body["findingCount"] == 0
    assert body["riskScore"] == 0
    assert body["level"] == "negligible"
    assert body["findings"] == []

    assert client.get("/api/scans/99999/risk").status_code == 404


def test_false_positive_finding_gates_score(client, monkeypatch):
    class FakeCleanAdapter:
        name = "fakeclean"
        target_types = ("email",)

        def run(self, target: str) -> ToolResult:
            return ToolResult(
                tool=self.name, status="completed",
                findings=[ToolFinding(type="email_exposure", title="fp", source="dns",
                                      evidence="synthetic", confidence="false_positive",
                                      severity="critical")],
                coverage={"sources_total": 1, "sources_checked": 1, "sources_failed": 0})

    import tools.registry as treg

    monkeypatch.setattr(treg, "build_registry",
                        lambda **kwargs: [FakeCleanAdapter(), FakeSearchAdapter()])
    r = client.post("/api/scans", json={"targetType": "email", "targetValue": "nora@example.com"})
    scan_id = r.json()["id"]
    assert client.post(f"/api/scans/{scan_id}/run").status_code == 200

    body = client.get(f"/api/scans/{scan_id}/risk").json()
    assert body["findingCount"] == 1
    row = body["findings"][0]
    assert row["riskScore"] == 0
    assert row["level"] == "negligible"
    assert row["breakdown"]["gated"] is True
    assert body["riskScore"] == 0