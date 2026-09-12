"""Audit log endpoints — recent activity, newest first (Phase 12 UI)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.backend import models as m
from app.backend.database.engine import get_db
from app.backend.schemas import (
    PAGE_SIZE_DEFAULT,
    PAGE_SIZE_MAX,
    LogOut,
    Paginated,
    pagination_meta,
)

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("")
def list_logs(
    entityType: str | None = None,
    actor: str | None = None,
    page: int = Query(1, ge=1),
    pageSize: int = Query(PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX),
    db: Session = Depends(get_db),
) -> Paginated[LogOut]:
    stmt = select(m.AuditLog)
    if entityType:
        stmt = stmt.where(m.AuditLog.entity_type == entityType)
    if actor:
        stmt = stmt.where(m.AuditLog.actor == actor)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
    rows = db.execute(
        stmt.order_by(m.AuditLog.id.desc()).offset((page - 1) * pageSize).limit(pageSize)
    ).scalars().all()
    return Paginated[LogOut](
        data=[LogOut.model_validate(r) for r in rows],
        pagination=pagination_meta(total, page, pageSize),
    )