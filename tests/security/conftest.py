"""Phase 13 security-test fixtures: isolated DB + upload dir + no AI backends."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

import app.backend.api.scans as scn
import app.backend.api.workers as wk
import app.backend.config as cfg
import app.backend.database.engine as eng


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_settings = cfg.Settings(
        database_path=str(tmp_path / "security.db"),
        upload_dir=str(tmp_path / "uploads"),
        upload_max_bytes=64 * 1024,
        ollama_url="",
        colab_ollama_url="",
        colab_job_dispatcher_url="",
    )
    monkeypatch.setattr(cfg, "settings", test_settings)
    monkeypatch.setattr(eng, "settings", test_settings)
    monkeypatch.setattr(wk, "settings", test_settings)
    monkeypatch.setattr(scn, "settings", test_settings)

    eng.engine = eng.build_engine(test_settings.database_path)
    eng.SessionLocal = sessionmaker(bind=eng.engine, autoflush=False, autocommit=False)
    eng.init_db()

    from app.backend.main import create_app

    return TestClient(create_app())


@pytest.fixture()
def db_session(tmp_path):
    engine = eng.init_db_at(str(tmp_path / "security_unit.db"))
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    yield session
    session.close()
    engine.dispose()