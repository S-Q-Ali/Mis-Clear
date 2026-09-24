"""Slice 1: filing-bundle download endpoint integration test (honest, no network).

Mirrors the removal API fixture (real registry, in-memory+tmp DB, TestClient);
uses the REAL zip builder. Honest assertions: real row markers only, nothing
fabricated, endpoint streams an honest member set with attachment headers.
"""

from __future__ import annotations

import json
import zipfile
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from tools.base import ToolFinding, ToolResult


class FakeGithubProfileAdapter:
    """Honest PSINT adapter producing one real confirmed finding (no network)."""

    name = "fakegithub"
    target_types = ("username",)
    registrable_domain = "github.com"

    def run(self, target: str) -> ToolResult:
        return ToolResult(
            tool=self.name,
            status="completed",
            findings=[
                ToolFinding(
                    type="profile_exposure",
                    title="public profile exposes email + phone",
                    source="github.com",
                    url="https://github.com/alice/profile",
                    evidence="verified on the public profile body",
                    confidence="confirmed",
                    severity="high",
                )
            ],
            coverage={"sources_total": 1, "sources_checked": 1, "sources_failed": 0},
        )


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app.backend import config as cfg
    from app.backend.api import workers as wk
    from app.backend.database import engine as eng
    from app.backend.services import job_dispatcher as jd

    test_settings = cfg.Settings(
        database_path=str(tmp_path / "fb_api.db"),
        ollama_url="", colab_ollama_url="",
        osint_enabled=True,
    )
    monkeypatch.setattr(cfg, "settings", test_settings)
    monkeypatch.setattr(wk, "settings", test_settings)
    monkeypatch.setattr(eng, "settings", test_settings)
    monkeypatch.setattr(jd, "settings", test_settings)

    engine_module = eng
    engine_module.engine = engine_module.build_engine(test_settings.database_path)
    engine_module.SessionLocal = sessionmaker(
        bind=engine_module.engine, autoflush=False, autocommit=False
    )
    engine_module.init_db()

    from app.backend.main import create_app

    with TestClient(create_app()) as c:
        yield c


def _scan_and_run(client: TestClient, monkeypatch) -> tuple[int, dict]:
    import tools.registry as treg

    monkeypatch.setattr(treg, "build_registry", lambda **kw: [FakeGithubProfileAdapter()])
    r = client.post("/api/scans", json={"targetType": "username", "targetValue": "alice"})
    assert r.status_code == 201
    scan_id = r.json()["id"]
    run = client.post(f"/api/scans/{scan_id}/run")
    assert run.status_code == 200 and run.json()["status"] == "completed"
    findings = client.get(f"/api/scans/{scan_id}/findings").json()["data"]
    assert findings, "honest bundle needs at least one real finding"
    return scan_id, findings[0]


def test_filing_bundle_downloads_real_zip_with_headed_attachment(client, monkeypatch):
    scan_id, _ = _scan_and_run(client, monkeypatch)

    resp = client.get(f"/api/scans/{scan_id}/filing-bundle")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/zip")
    assert "filing-bundle" in resp.headers["content-disposition"]
    assert resp.headers.get("x-filing-bundle-honesty", "").startswith("real-rows-only")

    with zipfile.ZipFile(BytesIO(resp.content)) as zf:
        members = set(zf.namelist())
        assert {
            "manifest.json", "findings.csv", "actions.csv", "executions.csv",
            "audit.log", "identity-graph.json", "risk-breakdown.json",
        } <= members
        manifest = json.loads(zf.read("manifest.json"))
        assert "generatedAt" in manifest
        assert "coverage" in manifest
        assert manifest["honesty"]["allRowsAreReal"] is True
        assert manifest["honesty"]["autoSent"] is False
        assert "github.com" in zf.read("findings.csv").decode()
        assert zf.read("actions.csv").decode()


def test_filing_bundle_404_when_scan_missing(client, monkeypatch):
    resp = client.get("/api/scans/999999/filing-bundle")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"
