"""Slice 4: NSFW adapter tests — severity mapping + Colab job lifecycle.

Contract (no fabricated verdicts):
  - unreadable file -> failed
  - worker completed  -> image_nsfw finding, severity from model category
  - worker failed/interrupted -> blocked, errors copied, no benign shortcut
  - benign result -> informational severity
"""

from __future__ import annotations

import io
from pathlib import Path

from tools.photo.nsfw import NsfwAdapter, _severity


def _png(tmp_path: Path) -> Path:
    from PIL import Image as PILImage

    p = tmp_path / "img.png"
    buf = io.BytesIO()
    PILImage.new("RGB", (32, 24), (10, 20, 30)).save(buf, format="PNG")
    p.write_bytes(buf.getvalue())
    return p


def _fresh_session(tmp_path):
    from sqlalchemy.orm import sessionmaker

    from app.backend.database.engine import init_db_at

    engine = init_db_at(str(tmp_path / "n.db"))
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def test_severity_mapping_deterministic():
    assert _severity('{"nsfw": true, "category": "adult", "confidence": 0.9}') == "critical"
    assert _severity('{"nsfw": true, "category": "explicit", "confidence": 0.95}') == "critical"
    assert _severity('{"nsfw": true, "category": "nudity", "confidence": 0.7}') == "high"
    assert _severity('{"nsfw": true, "category": "gore", "confidence": 0.6}') == "high"
    assert _severity('{"nsfw": false, "category": "benign", "confidence": 0.9}') == "informational"
    assert _severity("not json") == "medium"
    assert _severity("") == "medium"


def test_nsfw_unreadable_image_failed(tmp_path):
    p = tmp_path / "x.png"
    p.write_bytes(b"not-an-image")
    a = NsfwAdapter(strict_local=False)
    res = a.run(str(p))
    assert res.status == "failed"


def test_nsfw_local_mode_blocked_no_job(tmp_path, monkeypatch):
    from app.backend.services import vision_transport as vt

    called = {"n": 0}
    orig = vt.create_vision_job

    def _fake_create(*a, **kw):
        called["n"] += 1
        return orig(*a, **kw)

    monkeypatch.setattr(vt, "create_vision_job", _fake_create)
    a = NsfwAdapter(strict_local=True)
    res = a.run(str(_png(tmp_path)))
    assert res.status == "blocked"
    assert res.findings == []
    assert called["n"] == 0, "local mode must not create a Colab job"
    assert "hybrid" in res.errors[0]


def test_nsfw_completed_job_produces_finding(tmp_path, monkeypatch):
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
        job.result = {
            "ok": True,
            "text": '{"nsfw": true, "category": "adult", "confidence": 0.92, "note": "synthetic"}',
            "model": "gemma3:4b",
        }
        db_.commit()
        return job

    monkeypatch.setattr(vt, "run_job_sync", _fake_run)
    a = NsfwAdapter(strict_local=False, session_factory=lambda: S())
    res = a.run(str(_png(tmp_path)))
    assert res.status == "completed"
    assert len(res.findings) == 1
    assert res.findings[0].type == "image_nsfw"
    assert res.findings[0].severity == "critical"
    assert '"category": "adult"' in res.findings[0].evidence
    assert captured["job_type"] == "nsfw_analysis"
    assert captured["payload"]["image_base64"], "image bytes must travel in the job payload"


def test_nsfw_benign_result_informational(tmp_path, monkeypatch):
    from app.backend.services import vision_transport as vt

    S = _fresh_session(tmp_path)

    def _fake_run(db_, job_id, **_kw):
        from sqlalchemy import select

        from app.backend import models as m

        job = db_.execute(select(m.Job).where(m.Job.job_id == job_id)).scalar_one_or_none()
        job.status = "completed"
        job.result = {
            "ok": True,
            "text": '{"nsfw": false, "category": "benign", "confidence": 0.98, "note": "landscape"}',
            "model": "gemma3:4b",
        }
        db_.commit()
        return job

    monkeypatch.setattr(vt, "run_job_sync", _fake_run)
    a = NsfwAdapter(strict_local=False, session_factory=lambda: S())
    res = a.run(str(_png(tmp_path)))
    assert res.status == "completed"
    assert res.findings[0].severity == "informational"


def test_nsfw_failed_job_blocked_no_fabricated_verdict(tmp_path, monkeypatch):
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
    a = NsfwAdapter(strict_local=False, session_factory=lambda: S())
    res = a.run(str(_png(tmp_path)))
    assert res.status == "blocked"
    assert res.findings == []
    assert "GPU OOM" in res.errors
    assert "no fabricated verdict" in res.coverage.get("note", "")