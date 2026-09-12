"""Phase 6: scan orchestrator + POST /api/scans/{id}/run (fake adapters, no network)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.backend import models as m
from app.backend.database.engine import init_db_at
from tools.base import ToolFinding, ToolResult


# ---------- fake adapters ----------

class FakeEmailAdapter:
    name = "fakemail"
    target_types = ("email",)

    def run(self, target: str) -> ToolResult:
        return ToolResult(
            tool=self.name,
            status="completed",
            findings=[ToolFinding(type="email_account", title="found", source="fake",
                                  url="https://fake.test", evidence="synthetic fixture",
                                  confidence="probable", severity="medium")],
            coverage={"sources_total": 1, "sources_checked": 1, "sources_failed": 0},
        )


class FakeSearchAdapter:
    name = "fakesearch"
    target_types = ("email", "username", "custom")

    def run(self, target: str) -> ToolResult:
        return ToolResult(tool=self.name, status="completed",
                          coverage={"sources_total": 2, "sources_checked": 2, "sources_failed": 0})


class ExplodingAdapter:
    name = "boom"
    target_types = ("email",)

    def run(self, target: str) -> ToolResult:
        raise RuntimeError("boom")


# ---------- orchestrator ----------

def _fresh_session(tmp_path):
    engine = init_db_at(str(tmp_path / "osint.db"))
    return engine, Session(engine)


def test_orchestrator_persists_results_and_coverage(tmp_path):
    engine, session = _fresh_session(tmp_path)
    scan = m.Scan(target_type="email", target_value="alice@example.com", scan_mode="local")
    session.add(scan)
    session.commit()

    from app.backend.services.scan_orchestrator import run_scan
    run_scan(session, scan, registry=[FakeEmailAdapter(), FakeSearchAdapter()], timeout=1.0)

    session.expire_all()
    scan = session.get(m.Scan, scan.id)
    assert scan.status == "completed"
    assert scan.started_at is not None and scan.completed_at is not None
    assert scan.coverage["tools_ran"] == 2
    assert scan.coverage["findings"] == 1
    assert scan.error is None

    runs = session.execute(select(m.ToolRun).where(m.ToolRun.scan_id == scan.id)).scalars().all()
    assert len(runs) == 2
    assert all(r.status == "completed" for r in runs)
    assert next(r for r in runs if r.tool == "fakemail").findings_count == 1

    findings = session.execute(select(m.Finding).where(m.Finding.scan_id == scan.id)).scalars().all()
    assert len(findings) == 1
    assert findings[0].confidence == "probable" and findings[0].tool == "fakemail"

    identities = session.execute(select(m.Identity).where(m.Identity.scan_id == scan.id)).scalars().all()
    assert len(identities) >= 1  # target + Phase 9 graph-derived identities
    assert any(i.kind == "email" and i.value == "alice@example.com" for i in identities)


def test_orchestrator_tool_filter_and_crash_isolation(tmp_path):
    engine, session = _fresh_session(tmp_path)
    scan = m.Scan(target_type="email", target_value="bob@example.com")
    session.add(scan)
    session.commit()

    from app.backend.services.scan_orchestrator import run_scan
    run_scan(session, scan, registry=[FakeEmailAdapter(), FakeSearchAdapter(), ExplodingAdapter()],
             tool_filter=["fakemail", "boom"], timeout=1.0)

    session.expire_all()
    scan = session.get(m.Scan, scan.id)
    assert scan.status == "completed"
    assert scan.coverage["tools_ran"] == 2
    runs = session.execute(select(m.ToolRun).where(m.ToolRun.scan_id == scan.id)).scalars().all()
    assert len(runs) == 2
    boom = next(r for r in runs if r.tool == "boom")
    assert boom.status == "failed"
    assert "uncaught" in boom.errors[0]


def test_orchestrator_rejects_running_scan(tmp_path):
    engine, session = _fresh_session(tmp_path)
    scan = m.Scan(target_type="email", target_value="x@example.com", status="running")
    session.add(scan)
    session.commit()

    from app.backend.services.scan_orchestrator import run_scan
    with pytest.raises(ValueError):
        run_scan(session, scan, registry=[FakeEmailAdapter()])


# ---------- API run endpoint ----------

@pytest.fixture()
def client(tmp_path, monkeypatch):
    import app.backend.config as cfg
    import app.backend.database.engine as eng
    import app.backend.api.workers as wk
    import tools.registry as treg

    test_settings = cfg.Settings(
        database_path=str(tmp_path / "api.db"), ollama_url="", colab_ollama_url=""
    )
    monkeypatch.setattr(cfg, "settings", test_settings)
    monkeypatch.setattr(eng, "settings", test_settings)
    monkeypatch.setattr(wk, "settings", test_settings)

    eng.engine = eng.build_engine(test_settings.database_path)
    eng.SessionLocal = sessionmaker(bind=eng.engine, autoflush=False, autocommit=False)
    eng.init_db()

    monkeypatch.setattr(treg, "build_registry", lambda **kwargs: [FakeEmailAdapter(), FakeSearchAdapter()])

    from app.backend.main import create_app

    with TestClient(create_app()) as c:
        yield c


def test_run_endpoint_runs_scan_and_reports_results(client):
    r = client.post("/api/scans", json={"targetType": "email", "targetValue": "carol@example.com"})
    scan_id = r.json()["id"]
    run = client.post(f"/api/scans/{scan_id}/run")
    assert run.status_code == 200
    body = run.json()
    assert body["status"] == "completed"
    assert body["coverage"]["findings"] == 1

    findings = client.get(f"/api/scans/{scan_id}/findings")
    assert findings.json()["pagination"]["totalItems"] == 1
    assert findings.json()["data"][0]["tool"] == "fakemail"

    tool_runs = client.get(f"/api/scans/{scan_id}/tool-runs")
    assert tool_runs.json()["pagination"]["totalItems"] == 2


def test_run_endpoint_tool_filter(client):
    r = client.post("/api/scans", json={"targetType": "email", "targetValue": "dave@example.com"})
    scan_id = r.json()["id"]
    run = client.post(f"/api/scans/{scan_id}/run", json={"tools": ["fakemail"]})
    assert run.status_code == 200
    assert run.json()["coverage"]["tools_ran"] == 1
    tool_runs = client.get(f"/api/scans/{scan_id}/tool-runs")
    assert len(tool_runs.json()["data"]) == 1


def test_run_endpoint_404_and_missing_scan(client):
    assert client.post("/api/scans/99999/run").status_code == 404