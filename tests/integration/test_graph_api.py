"""Phase 9: identity graph API integration tests (fake adapters, no network)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from tools.base import ToolFinding, ToolResult


class FakeUsernameAdapter:
    name = "fakeuser"
    target_types = ("username",)

    def run(self, target: str) -> ToolResult:
        return ToolResult(
            tool=self.name,
            status="completed",
            findings=[ToolFinding(type="username_profile", title="Profile found",
                                  source="picsearch",
                                  url="https://example.com/u/alice",
                                  evidence="synthetic handle discovered",
                                  confidence="probable", severity="medium")],
            coverage={"sources_total": 1, "sources_checked": 1, "sources_failed": 0},
        )


class FakeSearchAdapter:
    name = "fakesearch"
    target_types = ("username", "email", "custom")

    def run(self, target: str) -> ToolResult:
        return ToolResult(tool=self.name, status="completed",
                          coverage={"sources_total": 2, "sources_checked": 2, "sources_failed": 0})


class FakeEmailAdapter:
    name = "fakemail"
    target_types = ("email",)

    def run(self, target: str) -> ToolResult:
        return ToolResult(
            tool=self.name, status="completed",
            findings=[ToolFinding(type="email_exposure", title="found", source="leakdb",
                                  url="https://leakdb.example/data", evidence="synthetic",
                                  confidence="probable", severity="medium")],
            coverage={"sources_total": 1, "sources_checked": 1, "sources_failed": 0},
        )


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


def test_graph_after_scan_links_username_chain(client, monkeypatch):
    import tools.registry as treg

    monkeypatch.setattr(treg, "build_registry",
                        lambda **kwargs: [FakeUsernameAdapter(), FakeSearchAdapter()])

    r = client.post("/api/scans", json={"targetType": "username", "targetValue": "alice"})
    scan_id = r.json()["id"]
    run = client.post(f"/api/scans/{scan_id}/run")
    assert run.status_code == 200 and run.json()["status"] == "completed"

    client.post(f"/api/scans/{scan_id}/graph/rebuild")
    g = client.get(f"/api/scans/{scan_id}/graph")
    assert g.status_code == 200
    body = g.json()
    kinds = {n["kind"] for n in body["nodes"]}
    assert "username" in kinds and "profile" in kinds
    assert "website" in kinds and "domain" in kinds and "source" in kinds
    edges = body["edges"]
    assert any(e["type"] == "username_profile" for e in edges)
    assert any(e["type"] == "exposure_site" for e in edges)
    assert any(e["type"] == "reported_by" for e in edges)
    assert all(e["evidenceFindingId"] is not None for e in edges)


def test_graph_rebuild_idempotent_and_cross_scan_merge(client, monkeypatch):
    import tools.registry as treg

    monkeypatch.setattr(treg, "build_registry",
                        lambda **kwargs: [FakeUsernameAdapter(), FakeSearchAdapter()])

    def _make_and_run(target):
        r = client.post("/api/scans", json={"targetType": "username", "targetValue": target})
        sid = r.json()["id"]
        assert client.post(f"/api/scans/{sid}/run").status_code == 200
        return sid

    a = _make_and_run("alice")
    _make_and_run("ALICE")

    rebuilt = client.post(f"/api/scans/{a}/graph/rebuild")
    assert rebuilt.status_code == 200
    body = rebuilt.json()
    user_nodes = [n for n in body["nodes"] if n["kind"] == "username"]
    assert len(user_nodes) == 1
    assert user_nodes[0]["canonical"] == "alice"
    assert user_nodes[0]["scanCount"] >= 2  # merged across the two scans


def test_graph_auto_linked_after_run(client, monkeypatch):
    import tools.registry as treg

    monkeypatch.setattr(treg, "build_registry",
                        lambda **kwargs: [FakeUsernameAdapter(), FakeSearchAdapter()])
    r = client.post("/api/scans", json={"targetType": "username", "targetValue": "carol"})
    scan_id = r.json()["id"]
    assert client.post(f"/api/scans/{scan_id}/run").status_code == 200
    body = client.get(f"/api/scans/{scan_id}/graph").json()
    assert any(n["kind"] == "profile" for n in body["nodes"])
    assert any(e["type"] == "username_profile" for e in body["edges"])


def test_graph_empty_and_404(client):
    r = client.post("/api/scans", json={"targetType": "email", "targetValue": "zoe@example.com"})
    scan_id = r.json()["id"]
    g = client.get(f"/api/scans/{scan_id}/graph")
    assert g.status_code == 200
    assert g.json() == {"nodes": [], "edges": []}

    assert client.get("/api/scans/99999/graph").status_code == 404
    assert client.post("/api/scans/99999/graph/rebuild").status_code == 404