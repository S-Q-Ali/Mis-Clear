"""Phase 14 E2E fixtures: real uvicorn server on loopback + real SQLite DB,
driven over genuine HTTP by httpx. Synthetic fixtures only."""

from __future__ import annotations

import socket
import threading
import time

import httpx
import pytest
import uvicorn
from sqlalchemy.orm import sessionmaker

from tools.base import ToolFinding, ToolResult


class FakeEmailAdapter:
    name = "fakemail"
    target_types = ("email",)

    def run(self, target: str) -> ToolResult:
        return ToolResult(
            tool=self.name,
            status="completed",
            findings=[ToolFinding(
                type="email_account",
                title="found",
                source="fake",
                url="https://fake.test",
                evidence="synthetic fixture",
                confidence="probable",
                severity="medium",
            )],
            coverage={"sources_total": 1, "sources_checked": 1, "sources_failed": 0},
        )


class FakeSearchAdapter:
    name = "fakesearch"
    target_types = ("email", "username", "custom")

    def run(self, target: str) -> ToolResult:
        return ToolResult(
            tool=self.name,
            status="completed",
            coverage={"sources_total": 2, "sources_checked": 2, "sources_failed": 0},
        )


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ServerManager:
    """Start/stop one uvicorn instance on an ephemeral loopback port."""

    def __init__(self, app: object) -> None:
        self.app = app
        self.port = _free_port()
        self.server: uvicorn.Server | None = None
        self.thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> ServerManager:
        config = uvicorn.Config(
            self.app, host="127.0.0.1", port=self.port, log_level="warning", lifespan="off"
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        for _ in range(200):
            if self.server.started:
                return self
            time.sleep(0.05)
        raise RuntimeError("uvicorn failed to start")

    def stop(self) -> None:
        if self.server is None:
            return
        self.server.should_exit = True
        if self.thread is not None:
            self.thread.join(timeout=10)


@pytest.fixture()
def e2e_settings(tmp_path, monkeypatch):
    """Temp DB/upload dir, no AI backends, fake OSINT registry (same process)."""
    import app.backend.api.scans as scn
    import app.backend.api.workers as wk
    import app.backend.config as cfg
    import app.backend.database.engine as eng
    import app.backend.services.job_dispatcher as jd
    import tools.registry as treg

    test_settings = cfg.Settings(
        database_path=str(tmp_path / "e2e.db"),
        upload_dir=str(tmp_path / "uploads"),
        ollama_url="",
        colab_ollama_url="",
    )
    for module in (cfg, eng, wk, jd, scn):
        monkeypatch.setattr(module, "settings", test_settings)

    eng.engine = eng.build_engine(test_settings.database_path)
    eng.SessionLocal = sessionmaker(bind=eng.engine, autoflush=False, autocommit=False)
    eng.init_db()

    monkeypatch.setattr(
        treg, "build_registry", lambda **kwargs: [FakeEmailAdapter(), FakeSearchAdapter()]
    )
    return test_settings, eng.SessionLocal


@pytest.fixture()
def e2e_app(e2e_settings):
    from app.backend.main import create_app

    return create_app()


@pytest.fixture()
def http(e2e_app):
    """Client + server manager; restarts are possible via the manager."""
    manager = ServerManager(e2e_app)
    manager.start()
    with httpx.Client(base_url=manager.base_url, timeout=30) as client:
        yield client, manager
    manager.stop()