"""Scan endpoints: create (idempotent), list (paginated), detail, sub-resources, run."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Query, Response, UploadFile
from fastapi import File as FastAPIFile
from PIL import Image as PILImage
from pydantic import BaseModel
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
    DeletionResearchOut,
    FindingOut,
    GraphOut,
    ImageOut,
    Paginated,
    ScanCreate,
    ScanOut,
    ScanRiskOut,
    ToolRunOut,
    pagination_meta,
)
from app.backend.services import deletion_research, idempotency, identity_graph, risk_engine
from app.backend.services.scan_orchestrator import run_scan

router = APIRouter(prefix="/api/scans", tags=["scans"])


class ScanRunRequest(BaseModel):
    """Optional tool subset for POST /api/scans/{id}/run."""

    tools: list[str] | None = None


@router.post("/{scan_id}/run", status_code=200)
def run_scan_endpoint(scan_id: int, body: ScanRunRequest | None = None, db: Session = Depends(get_db)) -> ScanOut:
    if not settings.osint_enabled:
        raise api_error(409, "OSINT_DISABLED", "OSINT tool adapters are disabled by configuration")
    scan = db.get(m.Scan, scan_id)
    if scan is None:
        raise api_error(404, "NOT_FOUND", f"Scan {scan_id} not found")
    run_scan(db, scan, tool_filter=body.tools if body and body.tools else None)
    updated = db.get(m.Scan, scan_id)
    return ScanOut.model_validate(updated)


@router.post("/{scan_id}/image", status_code=201)
async def upload_image(
    scan_id: int,
    file: UploadFile = FastAPIFile(...),
    db: Session = Depends(get_db),
) -> ScanOut:
    scan = db.get(m.Scan, scan_id)
    if scan is None:
        raise api_error(404, "NOT_FOUND", f"Scan {scan_id} not found")
    if scan.target_type != "image":
        raise api_error(400, "INVALID_TARGET_TYPE", "This scan was not created as targetType=image")
    if scan.status == "running":
        raise api_error(409, "SCAN_RUNNING", "Scan is already running")

    contents = await file.read()
    if len(contents) > settings.upload_max_bytes:
        raise api_error(413, "FILE_TOO_LARGE", f"Upload exceeds {settings.upload_max_bytes} bytes limit")
    if len(contents) == 0:
        raise api_error(422, "EMPTY_FILE", "Uploaded file is empty")

    try:
        probe = PILImage.open(BytesIO(contents))
        probe.verify()
    except Exception as exc:
        raise api_error(422, "INVALID_IMAGE", f"Not a valid image: {exc}") from exc

    # Decompression-bomb guard: a tiny file can declare huge dimensions and only
    # allocate on pixel load. Check the header before anything allocates pixels.
    with PILImage.open(BytesIO(contents)) as dims:
        width, height = dims.size
    if width * height > settings.upload_max_pixels:
        raise api_error(
            422,
            "IMAGE_TOO_LARGE",
            f"Image dimensions {width}x{height} exceed {settings.upload_max_pixels} pixels",
        )

    suffix = Path(file.filename or "").suffix.lower()[1:]
    suffix = "".join(c for c in suffix if c.isalnum())[:5] or "img"
    display_name = Path(file.filename or "image").name[:255]
    safe = f"{scan_id}_{uuid4().hex[:8]}.{suffix}"
    upload_basedir = Path(settings.upload_dir)
    upload_basedir.mkdir(parents=True, exist_ok=True)
    store_path = upload_basedir / safe
    store_path.write_bytes(contents)

    scan.target_value = str(store_path)
    db.add(
        m.Image(
            scan_id=scan.id,
            filename=display_name,
            local_path=str(store_path),
        )
    )
    scan.status = "pending"
    db.commit()
    run_scan(db, scan, tool_filter=None)
    updated = db.get(m.Scan, scan_id)
    return ScanOut.model_validate(updated)


@router.get("/{scan_id}/image")
def get_image(scan_id: int, db: Session = Depends(get_db)) -> ImageOut:
    image = db.execute(
        select(m.Image).where(m.Image.scan_id == scan_id).order_by(m.Image.id.desc())
    ).scalars().first()
    if image is None:
        raise api_error(404, "NOT_FOUND", f"No image stored for scan {scan_id}")
    return ImageOut.model_validate(image)


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


@router.get("/{scan_id}/graph")
def get_scan_graph(scan_id: int, db: Session = Depends(get_db)) -> GraphOut:
    if db.get(m.Scan, scan_id) is None:
        raise api_error(404, "NOT_FOUND", f"Scan {scan_id} not found")
    data = identity_graph.graph_for_scan(db, scan_id)
    return GraphOut(**data)


@router.post("/{scan_id}/graph/rebuild", status_code=200)
def rebuild_scan_graph(scan_id: int, db: Session = Depends(get_db)) -> GraphOut:
    scan = db.get(m.Scan, scan_id)
    if scan is None:
        raise api_error(404, "NOT_FOUND", f"Scan {scan_id} not found")
    identity_graph.rebuild_scan_graph(db, scan_id)
    db.add(m.AuditLog(actor="user", action="update", entity_type="scan", entity_id=scan.id,
                      detail="identity graph rebuilt"))
    db.commit()
    data = identity_graph.graph_for_scan(db, scan_id)
    return GraphOut(**data)


@router.get("/{scan_id}/risk")
def get_scan_risk(scan_id: int, db: Session = Depends(get_db)) -> ScanRiskOut:
    scan = db.get(m.Scan, scan_id)
    if scan is None:
        raise api_error(404, "NOT_FOUND", f"Scan {scan_id} not found")
    data = risk_engine.score_scan(db, scan_id)
    return ScanRiskOut(**data)


@router.post("/{scan_id}/deletion-research", status_code=200)
def run_deletion_research(scan_id: int, db: Session = Depends(get_db)) -> DeletionResearchOut:
    scan = db.get(m.Scan, scan_id)
    if scan is None:
        raise api_error(404, "NOT_FOUND", f"Scan {scan_id} not found")
    counts = deletion_research.research_scan(db, scan_id)
    db.add(m.AuditLog(actor="user", action="update", entity_type="scan", entity_id=scan.id,
                      detail=f"deletion research: {counts['created']} created, {counts['skipped']} skipped"))
    db.commit()
    return DeletionResearchOut(scanId=scan_id, **counts)