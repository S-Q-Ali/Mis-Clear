"""Phase 14 failure/recovery: job dispatcher survives transport failures.

A job that failed to submit (Colab dispatcher briefly down) is NOT silently
dropped: it stays tracked locally and can be recovered — either by a later
successful submit or by polling a completed result once the dispatcher returns.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from app.backend import models as m


class _Settings:
    colab_job_dispatcher_url = ""
    colab_request_timeout_seconds = 5


def _make_job(db, **kw) -> m.Job:
    job = m.Job(
        job_id="job-recovery-1",
        job_type="vision_analysis",
        status="queued",
        privacy_mode="hybrid_approved",
        payload={"prompt": "describe"},
        requested_capabilities=["vision"],
        expires_at=kw.pop("expires_at", datetime.now(UTC) + timedelta(minutes=5)),
        **kw,
    )
    db.add(job)
    db.flush()
    return job


class _DownTransport:
    """Transport whose handler raises; then the dispatcher 'recovers'."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        raise httpx.ConnectError("dispatcher unreachable")


def test_dispatcher_down_then_up_recovers_at_submit(db_session, monkeypatch):
    from app.backend.services import job_dispatcher

    monkeypatch.setattr(job_dispatcher, "settings", _Settings())
    job_dispatcher.settings.colab_job_dispatcher_url = "https://dispatch.example"  # type: ignore[attr-defined]

    job = _make_job(db_session)

    # Dispatcher down -> failure recorded, job stays queued (not dropped).
    down = _DownTransport()
    outcome = job_dispatcher.submit_job(
        db_session, job, client=httpx.Client(transport=httpx.MockTransport(down))
    )
    assert outcome["disposition"] == "failed"
    db_session.refresh(job)
    assert job.errors[0].startswith("dispatcher transfer failed")

    # Dispatcher back -> identical job submits successfully and is recovered.
    ok = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(201, json={"ok": True}))
    )
    outcome = job_dispatcher.submit_job(db_session, job, client=ok)
    assert outcome["disposition"] == "submitted"
    db_session.refresh(job)
    assert job.worker == "colab-dispatcher"
    assert len(job.errors) == 1  # history preserved, state recovered


def test_poll_recovers_failed_submit_to_completed(db_session, monkeypatch):
    from app.backend.services import job_dispatcher

    monkeypatch.setattr(job_dispatcher, "settings", _Settings())
    job_dispatcher.settings.colab_job_dispatcher_url = "https://dispatch.example"  # type: ignore[attr-defined]

    job = _make_job(db_session)
    down = _DownTransport()
    outcome = job_dispatcher.submit_job(
        db_session, job, client=httpx.Client(transport=httpx.MockTransport(down))
    )
    assert outcome["disposition"] == "failed"

    # Dispatcher recovered meanwhile; the queued job completes via poll.
    recovered = httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                json={
                    "protocol_version": "1",
                    "job_id": "job-recovery-1",
                    "status": "completed",
                    "result": {"text": "done"},
                    "errors": [],
                    "data_deleted": True,
                },
            )
        )
    )
    outcome = job_dispatcher.poll_job(db_session, job, client=recovered)
    assert outcome["disposition"] == "completed"
    db_session.refresh(job)
    assert job.status == "completed"
    assert job.result == {"text": "done"}