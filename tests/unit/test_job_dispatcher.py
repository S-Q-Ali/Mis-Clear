"""Phase 8: laptop job dispatcher service tests (MockTransport, no network)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.backend import models as m


class _Settings:
    colab_job_dispatcher_url = ""
    colab_request_timeout_seconds = 5


def _make_job(db, **kw) -> m.Job:
    default_expires = datetime.now(UTC) + timedelta(minutes=5)
    job = m.Job(
        job_id="job-dispatch-1",
        job_type="vision_analysis",
        status="queued",
        privacy_mode="hybrid_approved",
        payload={"prompt": "describe"},
        requested_capabilities=["vision"],
        expires_at=kw.pop("expires_at", default_expires),
        **kw,
    )
    db.add(job)
    db.flush()
    return job


# ---------- submit ----------

def test_submit_job_unconfigured_stays_queued(db_session, monkeypatch):
    from app.backend.services import job_dispatcher

    monkeypatch.setattr(job_dispatcher, "settings", _Settings())
    job = _make_job(db_session)
    outcome = job_dispatcher.submit_job(db_session, job)
    assert outcome == {"disposition": "unconfigured", "job_id": "job-dispatch-1"}
    db_session.refresh(job)
    assert job.status == "queued"
    assert job.errors == ["colab dispatcher not configured"]


def test_submit_job_posts_request_inbox(db_session, monkeypatch):
    from app.backend.services import job_dispatcher

    monkeypatch.setattr(job_dispatcher, "settings", _Settings())
    job_dispatcher.settings.colab_job_dispatcher_url = "https://dispatch.example"  # type: ignore[attr-defined]
    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        sent["path"] = request.url.path
        sent["body"] = _json.loads(request.content)
        return httpx.Response(201, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    job = _make_job(db_session)
    outcome = job_dispatcher.submit_job(db_session, job, client=client)
    assert outcome == {"disposition": "submitted", "job_id": "job-dispatch-1"}
    assert sent["path"] == "/jobs/inbox"
    body = sent["body"]
    assert body["job_id"] == "job-dispatch-1"
    assert body["job_type"] == "vision_analysis"
    assert body["protocol_version"] == "1"
    db_session.refresh(job)
    assert job.worker == "colab-dispatcher"
    assert job.status == "queued"


def test_submit_job_transport_failure_marks_error(db_session, monkeypatch):
    from app.backend.services import job_dispatcher

    monkeypatch.setattr(job_dispatcher, "settings", _Settings())
    job_dispatcher.settings.colab_job_dispatcher_url = "https://dispatch.example"  # type: ignore[attr-defined]

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    job = _make_job(db_session)
    outcome = job_dispatcher.submit_job(db_session, job, client=client)
    assert outcome == {"disposition": "failed", "job_id": "job-dispatch-1"}
    db_session.refresh(job)
    assert job.errors[0].startswith("dispatcher transfer failed")


# ---------- poll ----------

def test_poll_job_expired_interrupts_never_completed(db_session, monkeypatch):
    from app.backend.services import job_dispatcher

    monkeypatch.setattr(job_dispatcher, "settings", _Settings())
    job = _make_job(
        db_session,
        expires_at=datetime.now(UTC) - timedelta(seconds=10),
    )
    outcome = job_dispatcher.poll_job(db_session, job)
    assert outcome == {"disposition": "interrupted", "job_id": "job-dispatch-1"}
    db_session.refresh(job)
    assert job.status == "interrupted"
    assert "never auto-completed" in job.errors[-1]


def test_poll_job_collects_completed_result(db_session, monkeypatch):
    from app.backend.services import job_dispatcher

    monkeypatch.setattr(job_dispatcher, "settings", _Settings())
    job_dispatcher.settings.colab_job_dispatcher_url = "https://dispatch.example"  # type: ignore[attr-defined]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "protocol_version": "1",
            "job_id": "job-dispatch-1",
            "status": "completed",
            "result": {"ok": True, "text": "synthetic"},
            "errors": [],
            "data_deleted": True,
        })

    client = httpx.Client(transport=httpx.MockTransport(handler))
    job = _make_job(db_session)
    outcome = job_dispatcher.poll_job(db_session, job, client=client)
    assert outcome == {"disposition": "completed", "job_id": "job-dispatch-1"}
    db_session.refresh(job)
    assert job.status == "completed"
    assert job.data_deleted is True
    assert job.result == {"ok": True, "text": "synthetic"}


def test_poll_job_unconfigured_notes_error(db_session, monkeypatch):
    from app.backend.services import job_dispatcher

    monkeypatch.setattr(job_dispatcher, "settings", _Settings())
    job = _make_job(db_session)
    outcome = job_dispatcher.poll_job(db_session, job)
    assert outcome == {"disposition": "unconfigured", "job_id": "job-dispatch-1"}
    db_session.refresh(job)
    assert "colab dispatcher not configured" in job.errors


@pytest.fixture()
def db_session(tmp_path):
    from sqlalchemy.orm import Session

    from app.backend.database.engine import init_db_at

    engine = init_db_at(str(tmp_path / "dispatch.db"))
    session = Session(engine)
    yield session
    session.close()