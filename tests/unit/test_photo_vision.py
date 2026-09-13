"""Phase 15: photo vision/OCR transport — local Ollama vision (strict_local)
and Colab worker job transport (hybrid). Zero real network; fake router /
fake httpx / real temp SQLite for the job lifecycle.

Contract that matters (no fabricated results):
  - no backend (local or hybrid worker)  -> status=blocked, honest note
  - no image file readable               -> status=failed
  - hybrid job completed                 -> finding (type image_vision)
  - hybrid job failed/interrupted/timeout-> status=blocked, errors copied
"""

from __future__ import annotations

import io
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from sqlalchemy.orm import sessionmaker

from tools.photo.vision import VisionAdapter


def _png(tmp_path: Path) -> Path:
    from PIL import Image as PILImage

    p = tmp_path / "img.png"
    buf = io.BytesIO()
    PILImage.new("RGB", (32, 24), (10, 20, 30)).save(buf, format="PNG")
    p.write_bytes(buf.getvalue())
    return p


# ---------------- fake router / backend ----------------

@dataclass
class _FakeBackend:
    name: str = "fake-local"
    calls: list[dict] = field(default_factory=list)

    def available(self) -> bool:
        return True

    def generate(self, prompt: str, system: str | None = None, **kwargs):
        from app.backend.services.model_router import ModelResponse

        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        return ModelResponse(text="an outdoor photo of a coastline", model="gemma3:4b", backend=self.name, duration_ms=5)


class _FakeRouter:
    def __init__(self, backend) -> None:
        self._backend = backend

    def route(self, strict_local: bool = False):
        return self._backend


def _no_router():
    return _FakeRouter(None)


# ---------------- local (strict_local) path ----------------

def test_vision_local_ollama_produces_finding(tmp_path):
    be = _FakeBackend()
    a = VisionAdapter(router=_FakeRouter(be), strict_local=True)
    res = a.run(str(_png(tmp_path)))
    assert res.status == "completed"
    assert len(res.findings) == 1
    assert res.findings[0].type == "image_vision"
    assert res.findings[0].confidence == "probable"
    assert "coastline" in res.findings[0].evidence
    assert be.calls[0]["kwargs"].get("images"), "vision inference must send image bytes"


def test_vision_strict_local_no_backend_blocked(tmp_path):
    a = VisionAdapter(router=_no_router(), strict_local=True)
    res = a.run(str(_png(tmp_path)))
    assert res.status == "blocked"
    assert res.findings == []
    assert "no local AI vision backend available" in res.coverage.get("note", "")


def test_vision_unreadable_image_failed(tmp_path):
    p = tmp_path / "x.png"
    p.write_bytes(b"not-an-image")
    a = VisionAdapter(router=_FakeRouter(_FakeBackend()), strict_local=True)
    res = a.run(str(p))
    assert res.status == "failed"


# ---------------- hybrid job transport (real temp SQLite) ----------------

def _fresh_session(tmp_path):
    from app.backend.database.engine import init_db_at

    engine = init_db_at(str(tmp_path / "v.db"))
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def test_hybrid_run_job_completed(tmp_path):
    from app.backend.services import vision_transport as vt

    S = _fresh_session(tmp_path)
    db = S()
    try:
        job = vt.create_vision_job(db, job_type="vision_analysis", image_path=str(_png(tmp_path)),
                                   prompt="Describe", model="gemma3:4b", capabilities=["vision"], ttl_seconds=30)
        job.status = "completed"
        job.result = {"ok": True, "text": "a sunset over the ocean", "model": "gemma3:4b"}
        job.data_deleted = True
        db.commit()

        out = vt.run_job_sync(db, job.job_id, timeout_seconds=5, interval_seconds=0.0)
        assert out.status == "completed"
        assert out.result["text"] == "a sunset over the ocean"
        assert out.data_deleted is True
    finally:
        db.close()


def test_hybrid_run_job_times_out_honest(tmp_path):
    from app.backend.services import vision_transport as vt

    S = _fresh_session(tmp_path)
    db = S()
    try:
        job = vt.create_vision_job(db, job_type="vision_analysis", image_path=str(_png(tmp_path)),
                                   prompt="Describe", model="gemma3:4b", capabilities=["vision"], ttl_seconds=300)
        start = time.monotonic()
        out = vt.run_job_sync(db, job.job_id, timeout_seconds=0.2, interval_seconds=0.05)
        assert time.monotonic() - start < 2
        assert out.status == "interrupted"
        assert any("worker" in e.lower() for e in out.errors)
        assert "never auto-completed" in "\n".join(out.errors).lower()
    finally:
        db.close()


def test_hybrid_failed_job_returns_blocked(tmp_path, monkeypatch):
    from app.backend.services import vision_transport as vt

    S = _fresh_session(tmp_path)

    def _fake_run(db_, job_id, **_kw):
        from sqlalchemy import select

        from app.backend import models as m

        job = db_.execute(select(m.Job).where(m.Job.job_id == job_id)).scalar_one_or_none()
        job.status = "failed"
        job.errors = ["GPU OOM"]
        db_.commit()
        return job

    monkeypatch.setattr(vt, "run_job_sync", _fake_run)
    a = VisionAdapter(router=_no_router(), strict_local=False, session_factory=lambda: S())
    res = a.run(str(_png(tmp_path)))
    assert res.status == "blocked"
    assert "GPU OOM" in res.errors
    assert "failed" in res.coverage.get("note", "")


def test_hybrid_completed_job_produces_finding(tmp_path, monkeypatch):
    from app.backend.services import vision_transport as vt

    S = _fresh_session(tmp_path)
    captured: dict = {}

    def _fake_run(db_, job_id, **_kw):
        from sqlalchemy import select

        from app.backend import models as m

        job = db_.execute(select(m.Job).where(m.Job.job_id == job_id)).scalar_one_or_none()
        captured["job_type"] = job.job_type
        captured["payload"] = job.payload
        job.status = "completed"
        job.result = {"ok": True, "text": "two people in a room", "model": "gemma3:4b"}
        db_.commit()
        return job

    monkeypatch.setattr(vt, "run_job_sync", _fake_run)
    a = VisionAdapter(router=_no_router(), strict_local=False, session_factory=lambda: S())
    res = a.run(str(_png(tmp_path)))
    assert res.status == "completed"
    assert len(res.findings) == 1
    assert res.findings[0].type == "image_vision"
    assert "two people" in res.findings[0].evidence
    assert captured["job_type"] == "vision_analysis"
    assert captured["payload"]["image_base64"], "image bytes must travel in the job payload"


def test_hybrid_creates_job_via_dispatcher_when_configured(tmp_path, monkeypatch):
    from app.backend.services import vision_transport as vt

    S = _fresh_session(tmp_path)
    pushed: list[tuple] = []

    monkeypatch.setattr(vt.job_dispatcher, "dispatcher_base_url", lambda: "http://127.0.0.1:9999")

    def _fake_submit(db_, job):
        pushed.append((job.job_id, job.payload["image_base64"]))
        return {"disposition": "submitted"}

    monkeypatch.setattr(vt, "submit_job_to_colab", _fake_submit)

    def _fake_run(db_, job_id, **_kw):
        from sqlalchemy import select

        from app.backend import models as m

        j = db_.execute(select(m.Job).where(m.Job.job_id == job_id)).scalar_one_or_none()
        j.status = "completed"
        j.result = {"ok": True, "text": "a pier at dusk", "model": "gemma3:4b"}
        db_.commit()
        return j

    monkeypatch.setattr(vt, "run_job_sync", _fake_run)

    a = VisionAdapter(router=_no_router(), strict_local=False, session_factory=lambda: S())
    res = a.run(str(_png(tmp_path)))
    assert res.status == "completed"
    assert len(pushed) == 1, "job must be submitted when a dispatcher is configured"
    assert pushed[0][1], "image bytes must travel in the submitted payload"


# ---------------- worker-side handlers ----------------

def _fake_ollama_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        return httpx.Response(200, json={"response": "OLSR: found 'coastline'", "model": body["model"]})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_worker_vision_handler_sends_image_and_returns_text():
    from colab.capabilities import CapabilityReport
    from colab.handlers import get_handler

    client = _fake_ollama_client()
    cap = CapabilityReport(gpu=True, models=["gemma3:4b"])
    payload = {"image_base64": "aGVsbG8=", "prompt": "Describe this photo", "model": "gemma3:4b"}
    out = get_handler("vision_analysis")(payload, cap, client=client)
    assert out["ok"] is True
    assert "coastline" in out["text"]


def test_worker_vision_handler_blocks_without_capability():
    from colab.capabilities import CapabilityReport
    from colab.handlers import get_handler

    cap = CapabilityReport(gpu=False, models=[])
    out = get_handler("vision_analysis")({"image_base64": "aGVsbG8=", "model": "gemma3:4b"}, cap)
    assert out["ok"] is False


def test_worker_ocr_handler_rejects_without_gpu():
    from colab.capabilities import CapabilityReport
    from colab.handlers import get_handler

    out = get_handler("ocr")({"image_base64": "aGVsbG8="}, CapabilityReport(gpu=False, models=[]))
    assert out["ok"] is False
    assert "GPU" in out["note"]