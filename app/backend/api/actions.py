"""Privacy action endpoints (Phase 11): list, detail, human approve/decline gate."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.backend import models as m
from app.backend.database.engine import get_db
from app.backend.errors import api_error
from app.backend.schemas import (
    PAGE_SIZE_DEFAULT,
    PAGE_SIZE_MAX,
    ActionTransitionOut,
    Paginated,
    PrivacyActionOut,
    pagination_meta,
)
from app.backend.services import deletion_research

router = APIRouter(prefix="/api/actions", tags=["actions"])


@router.get("")
def list_actions(
    scanId: int | None = None,
    status: str | None = Query(None, pattern="^(pending|approved|declined|completed|expired)$"),
    page: int = Query(1, ge=1),
    pageSize: int = Query(PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX),
    db: Session = Depends(get_db),
) -> Paginated[PrivacyActionOut]:
    stmt = select(m.PrivacyAction)
    if scanId is not None:
        stmt = stmt.join(m.Finding).where(m.Finding.scan_id == scanId)
    if status:
        stmt = stmt.where(m.PrivacyAction.status == status)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
    rows = db.execute(
        stmt.order_by(m.PrivacyAction.id.desc()).offset((page - 1) * pageSize).limit(pageSize)
    ).scalars().all()
    return Paginated[PrivacyActionOut](
        data=[PrivacyActionOut.model_validate(r) for r in rows],
        pagination=pagination_meta(total, page, pageSize),
    )


@router.get("/{action_id}")
def get_action(action_id: int, db: Session = Depends(get_db)) -> PrivacyActionOut:
    action = db.get(m.PrivacyAction, action_id)
    if action is None:
        raise api_error(404, "NOT_FOUND", f"Privacy action {action_id} not found")
    return PrivacyActionOut.model_validate(action)


@router.post("/{action_id}/approve", status_code=200)
def approve_action(action_id: int, db: Session = Depends(get_db)) -> ActionTransitionOut:
    action = deletion_research.approve_action(db, action_id, actor="user")
    if action is None:
        raise api_error(404, "NOT_FOUND", f"Privacy action {action_id} not found")
    if action.status != "approved":
        raise api_error(409, "ACTION_NOT_PENDING",
                        f"Privacy action {action_id} cannot be approved from status {action.status}")
    db.commit()
    return ActionTransitionOut(id=action.id, status=action.status)


@router.post("/{action_id}/decline", status_code=200)
def decline_action(action_id: int, db: Session = Depends(get_db)) -> ActionTransitionOut:
    action = deletion_research.decline_action(db, action_id, actor="user")
    if action is None:
        raise api_error(404, "NOT_FOUND", f"Privacy action {action_id} not found")
    if action.status != "declined":
        raise api_error(409, "ACTION_NOT_PENDING",
                        f"Privacy action {action_id} cannot be declined from status {action.status}")
    db.commit()
    return ActionTransitionOut(id=action.id, status=action.status)