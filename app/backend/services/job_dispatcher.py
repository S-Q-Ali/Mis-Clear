"""Laptop-side job dispatcher (Phase 8).

Sends Job rows to the approved Colab dispatcher (or the worker's poll inbox),
and later collects the worker's JobResult. Honest degradation: if
`colab_job_dispatcher_url` is not configured the job stays queued with a
clear error — never a fabricated transfer, never an auto-"completed".
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from app.backend import models as m
from app.backend.config import settings
from app.backend.database.engine import Session
from colab.protocol import JobRequest, JobResult


def dispatcher_base_url() -> str:
    url = (settings.colab_job_dispatcher_url or "").strip()
    if not url.startswith(("http://", "https://")):
        return ""
    return url.rstrip("/")


def _timeout() -> int:
    return settings.colab_request_timeout_seconds


def submit_job(db: Session, job: m.Job, *, client: httpx.Client | None = None) -> dict[str, Any]:
    """Post the job to the Colab dispatcher inbox. Job stays queued when unconfigured."""
    base = dispatcher_base_url()
    if not base:
        job.errors = ["colab dispatcher not configured"]
        db.commit()
        return {"disposition": "unconfigured", "job_id": job.job_id}

    request = JobRequest(
        job_id=job.job_id,
        job_type=job.job_type,
        created_at=datetime.now(UTC).isoformat(),
        expires_at=job.expires_at.isoformat() if job.expires_at else "",
        privacy_mode=job.privacy_mode or "hybrid_approved",
        payload=job.payload or {},
        requested_capabilities=list(job.requested_capabilities or []),
    )
    try:
        with (client if client is not None else httpx.Client(timeout=_timeout())) as http:
            resp = http.post(f"{base}/jobs/inbox", json=request.to_dict())
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        job.errors = [f"dispatcher transfer failed: {exc}"]
        db.commit()
        return {"disposition": "failed", "job_id": job.job_id}

    job.worker = "colab-dispatcher"
    db.commit()
    return {"disposition": "submitted", "job_id": job.job_id}


def poll_job(db: Session, job: m.Job, *, client: httpx.Client | None = None, now=None) -> dict[str, Any]:
    """Fetch the worker's JobResult for one job; expire late jobs as interrupted."""
    base = dispatcher_base_url()
    now = now or datetime.now(UTC)
    expires = job.expires_at
    # SQLite round-trips DateTime as naive UTC; normalize before comparing.
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if expires is not None and expires < now and job.status in ("queued", "running"):
        job.status = "interrupted"
        job.errors = job.errors or []
        job.errors.append("job expired before worker completion (never auto-completed)")
        job.completed_at = now
        db.commit()
        return {"disposition": "interrupted", "job_id": job.job_id}
    if not base:
        if job.errors is None:
            job.errors = []
        if "colab dispatcher not configured" not in job.errors:
            job.errors.append("colab dispatcher not configured")
        db.commit()
        return {"disposition": "unconfigured", "job_id": job.job_id}

    try:
        with (client if client is not None else httpx.Client(timeout=_timeout())) as http:
            resp = http.get(f"{base}/jobs/{job.job_id}")
        resp.raise_for_status()
        result = JobResult.from_dict(resp.json())
    except httpx.HTTPError as exc:
        job.errors = job.errors or []
        job.errors.append(f"dispatcher poll failed: {exc}")
        db.commit()
        return {"disposition": "poll_failed", "job_id": job.job_id}

    if result.status in ("completed", "failed", "interrupted"):
        job.status = result.status
        job.result = result.result or None
        job.errors = result.errors or None
        job.data_deleted = bool(result.data_deleted)
        job.completed_at = now
    db.commit()
    return {"disposition": result.status, "job_id": job.job_id}