"""Laptop-side transport for photo vision/OCR jobs (Phase 15 wiring).

Hybrid scan mode sends the image (base64) inside the Job payload so the
approved Colab worker can run vision/OCR against the real pixels. The laptop
waits synchronously for the job to reach a terminal state, and can push the
job to a dispatcher inbox when one is configured. Timeout/expiry marks the job
interrupted with an honest note — a result is never fabricated.
"""

from __future__ import annotations

import base64
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backend import models as m
from app.backend.config import settings
from app.backend.services import job_dispatcher

_TERMINAL = ("completed", "failed", "interrupted")


def _get_job(db: Session, job_id: str) -> m.Job | None:
    return db.execute(select(m.Job).where(m.Job.job_id == job_id)).scalar_one_or_none()


def create_vision_job(
    db: Session,
    *,
    job_type: str,
    image_path: str,
    prompt: str,
    model: str,
    capabilities: list[str],
    ttl_seconds: int,
) -> m.Job:
    """Queue a vision/OCR job whose payload carries the image itself."""
    data = Path(image_path).read_bytes()
    job = m.Job(
        job_id=uuid4().hex,
        job_type=job_type,
        protocol_version="1",
        status="queued",
        privacy_mode="hybrid_approved",
        payload={
            "image_base64": base64.b64encode(data).decode("ascii"),
            "prompt": prompt,
            "model": model,
        },
        requested_capabilities=list(capabilities),
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
    )
    db.add(job)
    db.flush()
    db.add(
        m.AuditLog(
            actor="user",
            action="create",
            entity_type="job",
            entity_id=job.id,
            detail=f"{job_type}:{job.job_id} (photo transport)",
        )
    )
    db.commit()
    return job


def submit_job_to_colab(db: Session, job: m.Job) -> dict[str, Any]:
    """Push to the configured dispatcher inbox; no-op (queued) when unconfigured."""
    return job_dispatcher.submit_job(db, job)


def _normalize_expiry(expires_at):
    if expires_at is not None and expires_at.tzinfo is None:
        return expires_at.replace(tzinfo=UTC)
    return expires_at


def run_job_sync(
    db: Session,
    job_id: str,
    *,
    timeout_seconds: float | None = None,
    interval_seconds: float | None = None,
) -> m.Job:
    """Block until the job reaches a terminal state, expires, or times out.

    Caller owns the session. Expiry/timeout is recorded as `interrupted` with
    an explicit error — never an auto-completed result.
    """
    timeout = timeout_seconds if timeout_seconds is not None else settings.colab_job_timeout_seconds
    interval = interval_seconds if interval_seconds is not None else 0.25
    deadline = datetime.now(UTC) + timedelta(seconds=timeout)
    while True:
        job = _get_job(db, job_id)
        if job is None:
            return None
        if job.status in _TERMINAL:
            db.commit()
            return _get_job(db, job_id)
        now = datetime.now(UTC)
        expired = _normalize_expiry(job.expires_at)
        if now > deadline or (expired is not None and now > expired):
            job.status = "interrupted"
            job.errors = (job.errors or []) + [
                "no Colab worker completed this job; interrupted, never auto-completed"
            ]
            job.completed_at = now
            db.commit()
            return _get_job(db, job_id)
        # Commit between polls: SQLite read transactions hold a SHARED lock that
        # would otherwise starve the worker's writer transitions.
        db.commit()
        time.sleep(interval)