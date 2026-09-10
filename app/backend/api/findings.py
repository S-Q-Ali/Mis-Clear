"""Findings endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.backend import models as m
from app.backend.database.engine import get_db
from app.backend.errors import api_error
from app.backend.schemas import FindingOut

router = APIRouter(prefix="/api/findings", tags=["findings"])


@router.get("/{finding_id}")
def get_finding(finding_id: int, db: Session = Depends(get_db)) -> FindingOut:
    finding = db.get(m.Finding, finding_id)
    if finding is None:
        raise api_error(404, "NOT_FOUND", f"Finding {finding_id} not found")
    return FindingOut.model_validate(finding)