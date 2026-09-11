"""Scan orchestrator — runs adapters for a scan and persists results.

Pipeline (master plan §12):
    - OSINT scans (email/username/custom): adapter chain via tools/registry.
    - Photo scans (image): local-first photo forensics chain via tools/photo.

Network is only ever *read* (public OSINT). Web content is untrusted input.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backend import models as m
from tools.base import ToolResult


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _compact_coverage(coverage: dict[str, Any]) -> str:
    parts = [f"{k}={v}" for k, v in coverage.items() if v not in (None, "")]
    return ";".join(parts)[:255]


def _persist_image_row(
    db: Session,
    scan: m.Scan,
    target_path: str,
    findings: list,
) -> None:
    """Persist an Image row from photo scan results (skip if one already exists)."""
    existing = db.execute(
        select(m.Image).where(m.Image.scan_id == scan.id).limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        md5 = sha = phash = None
        for f in findings:
            if f.type == "image_hash":
                for line in (f.evidence or "").split("\n"):
                    if line.startswith("md5="):
                        md5 = line[4:]
                    elif line.startswith("sha256="):
                        sha = line[7:]
            elif f.type == "image_perceptual_hash":
                ev = f.evidence or ""
                if "phash=" in ev:
                    phash = ev.split("phash=", 1)[1].split("\n")[0]
        existing.md5 = md5 or existing.md5
        existing.sha256 = sha or existing.sha256
        existing.phash = phash or existing.phash
        db.flush()
        return
    img = m.Image(
        scan_id=scan.id,
        filename=Path(target_path).name,
        local_path=target_path,
    )
    for f in findings:
        if f.type == "image_hash":
            for line in (f.evidence or "").split("\n"):
                if line.startswith("md5="):
                    img.md5 = line[4:]
                elif line.startswith("sha256="):
                    img.sha256 = line[7:]
        elif f.type == "image_perceptual_hash":
            ev = f.evidence or ""
            if "phash=" in ev:
                img.phash = ev.split("phash=", 1)[1].split("\n")[0]
    db.add(img)
    db.flush()
    return img


def run_scan(
    db: Session,
    scan: m.Scan,
    *,
    registry: list | None = None,
    tool_filter: list[str] | None = None,
    build_registry: Callable[..., list] | None = None,
    timeout: float | None = None,
) -> m.Scan:
    """Execute adapters for `scan` and persist results. Returns the updated scan."""
    db.refresh(scan)
    if scan.status == "running":
        raise ValueError("scan is already running")

    from app.backend.config import settings

    adapter_timeout = timeout if timeout is not None else settings.osint_timeout_seconds

    is_image = scan.target_type == "image"

    if registry is not None:
        adapters = registry
    elif is_image:
        from tools.photo.registry import photo_pipeline

        strict_local = scan.scan_mode != "hybrid"
        adapters = photo_pipeline(strict_local=strict_local)
    else:
        from tools.registry import build_registry as default_build

        builder = build_registry or default_build
        adapters = builder(timeout=adapter_timeout)

    if tool_filter:
        wanted = set(tool_filter)
        adapters = [a for a in adapters if a.name in wanted]

    scan.status = "running"
    scan.started_at = _utcnow()
    scan.error = None
    db.commit()

    aggregate: dict[str, Any] = {"tools_ran": 0, "sources_checked": 0, "sources_total": 0, "findings": 0}
    all_findings: list[m.Finding] = []
    for adapter in adapters:
        tool_run = m.ToolRun(scan_id=scan.id, tool=adapter.name, status="running")
        db.add(tool_run)
        db.flush()
        try:
            result: ToolResult = adapter.run(scan.target_value)
        except Exception as exc:  # noqa: BLE001 - adapter contract says no raise; stay resilient
            result = ToolResult(tool=adapter.name, status="failed", errors=[f"uncaught: {exc}"])

        tool_run.status = result.status
        tool_run.duration_ms = result.duration_ms
        tool_run.coverage = _compact_coverage(result.coverage)
        tool_run.findings_count = len(result.findings)
        tool_run.errors = result.errors or None
        tool_run.raw_reference = result.raw_reference
        tool_run.completed_at = _utcnow()

        for finding in result.findings:
            db_finding = m.Finding(
                scan_id=scan.id,
                type=finding.type,
                title=finding.title,
                source=finding.source,
                url=finding.url,
                evidence=finding.evidence,
                confidence=finding.confidence,
                severity=finding.severity,
                scope=finding.scope,
                tool=adapter.name,
            )
            db.add(db_finding)
            all_findings.append(db_finding)
        cc = result.coverage
        aggregate["tools_ran"] += 1
        aggregate["sources_checked"] += int(cc.get("sources_checked", 0))
        aggregate["sources_total"] += int(cc.get("sources_total", 0))
        aggregate["findings"] += len(result.findings)
        db.commit()

    if is_image:
        _persist_image_row(db, scan, scan.target_value, all_findings)

    db.add(
        m.Identity(
            scan_id=scan.id,
            kind=scan.target_type,
            value=scan.target_value,
            canonical=scan.target_value.strip().lower(),
        )
    )
    scan.status = "completed"
    scan.completed_at = _utcnow()
    scan.coverage = aggregate
    if aggregate["sources_checked"] == 0 and aggregate["findings"] == 0:
        scan.error = "no data found (network disabled or nothing found)"
    db.commit()
    db.refresh(scan)
    return scan