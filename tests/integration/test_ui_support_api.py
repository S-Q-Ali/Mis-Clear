"""Phase 12 UI support: /api/logs and read-only /api/settings integration tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.backend import models as m


@pytest.fixture()
def ctx(tmp_path, monkeypatch):
    import app.backend.api.workers as wk
    import app.backend.config as cfg
    import app.backend.database.engine as eng
    import app.backend.services.job_dispatcher as jd

    test_settings = cfg.Settings(
        database_path=str(tmp_path / "ui.db"), ollama_url="", colab_ollama_url=""
    )
    monkeypatch.setattr(cfg, "settings", test_settings)
    monkeypatch.setattr(eng, "settings", test_settings)
    monkeypatch.setattr(wk, "settings", test_settings)
    monkeypatch.setattr(jd, "settings", test_settings)

    eng.engine = eng.build_engine(test_settings.database_path)
    eng.SessionLocal = sessionmaker(bind=eng.engine, autoflush=False, autocommit=False)
    eng.init_db()

    yield eng.SessionLocal


@pytest.fixture()
def api(ctx):
    from app.backend.main import create_app

    with TestClient(create_app()) as c:
        yield c


def test_logs_newest_first_and_filter(ctx, api):
    db = ctx()
    db.add_all([
        m.AuditLog(actor="user", action="create", entity_type="scan", entity_id=1, detail="first"),
        m.AuditLog(actor="user", action="run", entity_type="scan", entity_id=1, detail="second"),
        m.AuditLog(actor="system", action="update", entity_type="scan", entity_id=1, detail="third"),
    ])
    db.commit()
    db.close()

    body = api.get("/api/logs").json()
    rows = body["data"]
    assert body["pagination"]["totalItems"] == 3
    assert [r["detail"] for r in rows] == ["third", "second", "first"]
    assert rows[0]["entityType"] == "scan"

    filtered = api.get("/api/logs", params={"actor": "user"}).json()
    assert filtered["pagination"]["totalItems"] == 2


def test_settings_read_only_and_no_write(api):
    body = api.get("/api/settings").json()
    assert body["readOnly"] is True
    assert body["osintEnabled"] is True
    assert body["defaultScanMode"] == "local"
    assert body["colabApprovalRequired"] is True
    assert body["localAiConfigured"] is False  # ollama_url="" in test fixture

    assert api.post("/api/settings").status_code == 405
    assert api.put("/api/settings").status_code == 405