"""Scan endpoints: create (idempotent), list (paginated), detail, sub-resources."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.backend import models as m
from app.backend.config import settings
from app.backend.database.engine import get_db
from app.backend.errors import api_error
from app.backend.schemas import (
    PAGE_SIZE_DEFAULT,
    PAGE_SIZE_MAX,
    ScanCreate,
    ScanOut,
    ToolRunOut,
    FindingOut,
    Paginated,
    pagination_meta,
)
from app.backend.services import idempotency

router = APIRouter(prefix="/api/scans", tags=["scans"])


@router.post("", status_code=201)
def create_scan(
    body: ScanCreate,
    response: Response,
    x_idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> ScanOut:
    payload: dict[str, Any] = {"targetType": body.targetType, "targetValue": body.targetValue, "scanMode": body.scanMode}

    if x_idempotency_key:
        try:
            claim = idempotency.claim(db, x_idempotency_key, payload)
        except IntegrityError:
            db.rollback()
            claim = idempotency.replay(db, x_idempotency_key, payload)
        if claim.disposition == "mismatch":
            raise api_error(422, "IDEMPOTENCY_MISMATCH", "Idempotency-Key reused with a different payload")
        if claim.disposition == "inflight":
            raise api_error(409, "IDEMPOTENCY_IN_FLIGHT", "A request with this Idempotency-Key is already being processed")
        if claim.disposition == "replay" and claim.scan is not None:
            response.status_code = 200
            return ScanOut.model_validate(claim.scan)

    scan = m.Scan(
        target_type=body.targetType,
        target_value=body.targetValue,
        scan_mode=body.scanMode,
        status="pending",
    )
    db.add(scan)
    db.flush()
    if x_idempotency_key:
        row = db.execute(select(m.IdempotencyKey).where(m.IdempotencyKey.key == x_idempotency_key)).scalar_one()
        row.scan_id = scan.id
    db.add(m.AuditLog(actor="user", action="create", entity_type="scan", entity_id=scan.id,
                      detail=f"{body.targetType}:{body.targetValue}"))
    db.commit()
    return ScanOut.model_validate(scan)


@router.get("")
def list_scans(
    page: int = Query(1, ge=1),
    pageSize: int = Query(PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> Paginated[ScanOut]:
    stmt = select(m.Scan)
    if status:
        stmt = stmt.where(m.Scan.status == status)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
    rows = db.execute(stmt.order_by(m.Scan.id.desc()).offset((page - 1) * pageSize).limit(pageSize)).scalars().all()
    return Paginated[ScanOut](data=[ScanOut.model_validate(r) for r in rows],
                              pagination=pagination_meta(total, page, pageSize))


@router.get("/{scan_id}")
def get_scan(scan_id: int, db: Session = Depends(get_db)) -> ScanOut:
    scan = db.get(m.Scan, scan_id)
    if scan is None:
        raise api_error(404, "NOT_FOUND", f"Scan {scan_id} not found")
    return ScanOut.model_validate(scan)


@router.get("/{scan_id}/findings")
def list_findings(
    scan_id: int,
    page: int = Query(1, ge=1),
    pageSize: int = Query(PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX),
    db: Session = Depends(get_db),
) -> Paginated[FindingOut]:
    if db.get(m.Scan, scan_id) is None:
        raise api_error(404, "NOT_FOUND", f"Scan {scan_id} not found")
    stmt = select(m.Finding).where(m.Finding.scan_id == scan_id)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
    rows = db.execute(stmt.order_by(m.Finding.id.desc()).offset((page - 1) * pageSize).limit(pageSize)).scalars().all()
    return Paginated[FindingOut](data=[FindingOut.model_validate(r) for r in rows],
                                 pagination=pagination_meta(total, page, pageSize))


@router.get("/{scan_id}/tool-runs")
def list_tool_runs(
    scan_id: int,
    page: int = Query(1, ge=1),
    pageSize: int = Query(PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX),
    db: Session = Depends(get_db),
) -> Paginated[ToolRunOut]:
    if db.get(m.Scan, scan_id) is None:
        raise api_error(404, "NOT_FOUND", f"Scan {scan_id} not found")
    stmt = select(m.ToolRun).where(m.ToolRun.scan_id == scan_id)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
    rows = db.execute(stmt.order_by(m.ToolRun.id.desc()).offset((page - 1) * pageSize).limit(pageSize)).scalars().all()
    return Paginated[ToolRunOut](data=[ToolRunOut.model_validate(r) for r in rows],
                                 pagination=pagination_meta(total, page, pageSize))