"""Health endpoint contract: the canonical route is /health (root).

The frontend health ping must not hit /api/health — that path is reserved for
APIRouter-mounted endpoints and is deliberately absent here.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import app.backend.config as cfg
    import app.backend.database.engine as eng

    test_settings = cfg.Settings(
        database_path=str(tmp_path / "health.db"), ollama_url="", colab_ollama_url=""
    )
    monkeypatch.setattr(cfg, "settings", test_settings)
    monkeypatch.setattr(eng, "settings", test_settings)

    eng.engine = eng.build_engine(test_settings.database_path)
    eng.SessionLocal = sessionmaker(bind=eng.engine, autoflush=False, autocommit=False)
    eng.init_db()

    from app.backend.main import create_app

    with TestClient(create_app()) as c:
        yield c


def test_health_served_at_root(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "privacy-guardian"


def test_api_health_path_is_not_a_route(client):
    """Guards against frontend drift back to /api/health (404s at runtime)."""
    r = client.get("/api/health")
    assert r.status_code == 404