"""Job endpoints (Colab worker protocol mirror)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
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


@router.get("/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)) -> JobOut:
    job = db.get(m.Job, job_id)
    if job is None:
        raise api_error(404, "NOT_FOUND", f"Job {job_id} not found")
    return JobOut.model_validate(job)