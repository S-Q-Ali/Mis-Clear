"""Evidence-based report summary for a scan (aggregations only — no invention)."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backend import models as m
from app.backend.api.workers import worker_status
from app.backend.database.engine import get_db
from app.backend.errors import api_error
from app.backend.schemas import ReportSummary, ScanOut

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/{scan_id}")
def report_summary(scan_id: int, db: Session = Depends(get_db)) -> ReportSummary:
    scan = db.get(m.Scan, scan_id)
    if scan is None:
        raise api_error(404, "NOT_FOUND", f"Scan {scan_id} not found")

    findings = db.execute(select(m.Finding).where(m.Finding.scan_id == scan_id)).scalars().all()
    by_severity: dict[str, int] = {}
    by_confidence: dict[str, int] = {}
    sources: set[str] = set()
    for f in findings:
        by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
        by_confidence[f.confidence] = by_confidence.get(f.confidence, 0) + 1
        if f.tool:
            sources.add(f.tool)
    tools_run = db.execute(select(m.ToolRun).where(m.ToolRun.scan_id == scan_id)).scalars().all()
    tool_names = [t.tool for t in tools_run]

    ai = worker_status()
    return ReportSummary(
        scan=ScanOut.model_validate(scan),
        totalFindings=len(findings),
        bySeverity=by_severity,
        byConfidence=by_confidence,
        toolsRun=len(tools_run),
        sourcesChecked=sorted(tool_names) or sorted(sources),
        aiAvailable=ai.localAiAvailable or ai.colabAiAvailable,
    )