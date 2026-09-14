"""Findings endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backend import models as m
from app.backend.database.engine import get_db
from app.backend.errors import api_error
from app.backend.schemas import FindingOut, RemovalOut
from app.backend.services import deletion_research
from app.backend.services.removal_executor import execution_summary, start_removal

router = APIRouter(prefix="/api/findings", tags=["findings"])


def _action_for(db: Session, finding_id: int) -> m.PrivacyAction | None:
    return db.execute(
        select(m.PrivacyAction).where(m.PrivacyAction.finding_id == finding_id)
    ).scalars().first()


@router.get("/{finding_id}")
def get_finding(finding_id: int, db: Session = Depends(get_db)) -> FindingOut:
    finding = db.get(m.Finding, finding_id)
    if finding is None:
        raise api_error(404, "NOT_FOUND", f"Finding {finding_id} not found")
    out = FindingOut.model_validate(finding)
    action = _action_for(db, finding_id)
    out.actionId = action.id if action else None
    return out


@router.post("/{finding_id}/remove", status_code=200)
def remove_finding(finding_id: int, db: Session = Depends(get_db)) -> RemovalOut:
    """Per-finding 'Remove data' button (Phase 16): human approval gate.

    Ensures a researched action exists for the finding (research runs if it was
    never requested), then runs the removal ladder. The returned `status` is the
    verified outcome (removed / still_present / requires_manual / verified via
    escalation) — never fabricated.
    """
    finding = db.get(m.Finding, finding_id)
    if finding is None:
        raise api_error(404, "NOT_FOUND", f"Finding {finding_id} not found")

    action = _action_for(db, finding_id)
    if action is None:
        if not deletion_research.is_candidate(finding):
            raise api_error(409, "NOT_REMOVABLE",
                            f"Finding {finding_id} is not a research candidate")
        action = deletion_research.research_finding(db, finding)
        db.flush()

    if action.status not in ("pending", "approved"):
        raise api_error(409, "ACTION_NOT_REMOVABLE",
                        f"Action for finding {finding_id} is {action.status}")

    exec_row = start_removal(db, action.id)
    db.refresh(action)
    return RemovalOut(
        findingId=finding_id,
        actionId=action.id,
        status=action.status,
        execution=execution_summary(exec_row),
    )