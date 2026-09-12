"""Job endpoints (Colab worker protocol mirror)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.backend import models as m
from app.backend.database.engine import get_db
from app.backend.errors import api_error
from app.backend.schemas import (
    PAGE_SIZE_DEFAULT,
    PAGE_SIZE_MAX,
    JobCreate,
    JobOut,
    Paginated,
    pagination_meta,
)
from app.backend.services import job_dispatcher

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", status_code=201)
def create_job(body: JobCreate, db: Session = Depends(get_db)) -> JobOut:
    if body.scanId is not None and db.get(m.Scan, body.scanId) is None:
        raise api_error(404, "NOT_FOUND", f"Scan {body.scanId} not found")
    existing = db.execute(select(m.Job).where(m.Job.job_id == body.jobId)).scalar_one_or_none()
    if existing is not None:
        same = (
            existing.job_type == body.jobType
            and existing.privacy_mode == body.privacyMode
            and existing.payload == body.payload
        )
        if not same:
            raise api_error(409, "JOB_CONFLICT", f"Job {body.jobId} already exists with a different definition")
        return JobOut.model_validate(existing)
    job = m.Job(
        job_id=body.jobId,
        scan_id=body.scanId,
        job_type=body.jobType,
        protocol_version="1",
        status="queued",
        privacy_mode=body.privacyMode,
        payload=body.payload,
        requested_capabilities=body.requestedCapabilities,
        expires_at=body.expiresAt,
    )
    try:
        db.add(job)
        db.flush()
        db.add(m.AuditLog(actor="user", action="create", entity_type="job", entity_id=job.id,
                          detail=f"{body.jobType}:{body.jobId}"))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise api_error(409, "JOB_CONFLICT", f"Job {body.jobId} already exists")
    return JobOut.model_validate(job)


@router.get("")
def list_jobs(
    page: int = Query(1, ge=1),
    pageSize: int = Query(PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> Paginated[JobOut]:
    stmt = select(m.Job)
    if status:
        stmt = stmt.where(m.Job.status == status)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
    rows = db.execute(stmt.order_by(m.Job.id.desc()).offset((page - 1) * pageSize).limit(pageSize)).scalars().all()
    return Paginated[JobOut](data=[JobOut.model_validate(r) for r in rows],
                             pagination=pagination_meta(total, page, pageSize))


# GET /next MUST be defined before GET /{job_id} (int) to avoid 422 on "next".
@router.get("/next", status_code=200, response_model=None)
def get_next_job(db: Session = Depends(get_db)) -> Response:
    """Return the oldest queued job for a Colab worker, or 204 if none."""
    now = datetime.now(UTC)
    # Expire any stale queued/running jobs first (honest status).
    stale = db.execute(
        select(m.Job).where(
            m.Job.status.in_(["queued", "running"]),
            m.Job.expires_at.isnot(None),
            m.Job.expires_at < now,
        )
    ).scalars().all()
    for job in stale:
        job.status = "interrupted"
        job.errors = (job.errors or []) + ["job expired before worker pickup (never auto-completed)"]
        job.completed_at = now
    if stale:
        db.commit()

    job = db.execute(
        select(m.Job)
        .where(m.Job.status == "queued")
        .order_by(m.Job.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()

    if job is None:
        return Response(status_code=204)

    # Mark running so it won't be double-dispatched.
    job.status = "running"
    job.started_at = now
    db.add(m.AuditLog(
        actor="colab-worker",
        action="run",
        entity_type="job",
        entity_id=job.id,
        detail=f"worker-pickup:{job.job_type}:{job.job_id}",
    ))
    db.commit()

    body = json.dumps({
        "protocol_version": job.protocol_version,
        "job_id": job.job_id,
        "job_type": job.job_type,
        "created_at": job.created_at.isoformat() if job.created_at else "",
        "expires_at": job.expires_at.isoformat() if job.expires_at else "",
        "privacy_mode": job.privacy_mode,
        "payload": job.payload or {},
        "requested_capabilities": job.requested_capabilities or [],
        "return_format": "json",
        "_internal_id": job.id,
    })
    return Response(content=body, media_type="application/json")


@router.get("/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)) -> JobOut:
    job = db.get(m.Job, job_id)
    if job is None:
        raise api_error(404, "NOT_FOUND", f"Job {job_id} not found")
    return JobOut.model_validate(job)


@router.post("/{job_id}/dispatch")
def dispatch_job(job_id: int, db: Session = Depends(get_db)) -> JobOut:
    job = db.get(m.Job, job_id)
    if job is None:
        raise api_error(404, "NOT_FOUND", f"Job {job_id} not found")
    if job.status == "running":
        raise api_error(409, "JOB_RUNNING", "Job is already dispatched")
    outcome = job_dispatcher.submit_job(db, job)
    db.add(m.AuditLog(actor="user", action="run", entity_type="job", entity_id=job.id,
                      detail=f"dispatch:{outcome['disposition']}"))
    db.commit()
    return JobOut.model_validate(db.get(m.Job, job_id))

@router.post("/{job_id}/poll")
def poll_job(job_id: int, db: Session = Depends(get_db)) -> JobOut:
    job = db.get(m.Job, job_id)
    if job is None:
        raise api_error(404, "NOT_FOUND", f"Job {job_id} not found")
    outcome = job_dispatcher.poll_job(db, job)
    db.add(m.AuditLog(actor="user", action="update", entity_type="job", entity_id=job.id,
                      detail=f"poll:{outcome['disposition']}"))
    db.commit()
    return JobOut.model_validate(db.get(m.Job, job_id))


@router.post("/{job_id}/result")
def post_job_result(job_id: str, body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
    """Accept a JobResult from a Colab worker and persist it."""
    job = db.execute(select(m.Job).where(m.Job.job_id == job_id)).scalar_one_or_none()
    if job is None:
        raise api_error(404, "NOT_FOUND", f"Job {job_id} not found")

    status = body.get("status", "interrupted")
    if status not in ("completed", "failed", "interrupted"):
        raise api_error(422, "INVALID_STATUS", f"Unexpected result status: {status}")

    job.status = status
    job.result = body.get("result")
    job.errors = body.get("errors")
    job.data_deleted = bool(body.get("data_deleted", False))
    job.completed_at = datetime.now(UTC)

    db.add(m.AuditLog(
        actor="colab-worker",
        action="update",
        entity_type="job",
        entity_id=job.id,
        detail=f"worker-result:{status}:data_deleted={job.data_deleted}",
    ))
    db.commit()
    return {"ok": True, "job_id": job_id, "status": status}