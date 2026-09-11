"""Scan orchestrator — runs the OSINT adapters for a scan and persists results.

Pipeline (master plan §12, OSINT subset): for each selected adapter,
    ToolRun row (running) → adapter.run(target) → persist findings + identities
    → ToolRun completed/failed → scan completed with honest coverage.

Network is only ever *read* (public OSINT). Web content is untrusted input.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.backend import models as m
from tools.base import ToolResult


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _compact_coverage(coverage: dict[str, Any]) -> str:
    parts = [f"{k}={v}" for k, v in coverage.items() if v not in (None, "")]
    return ";".join(parts)[:255]


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
    from tools.registry import build_registry as default_build

    builder = build_registry or default_build
    adapters = registry if registry is not None else builder(timeout=adapter_timeout)
    if tool_filter:
        wanted = set(tool_filter)
        adapters = [a for a in adapters if a.name in wanted]

    scan.status = "running"
    scan.started_at = _utcnow()
    scan.error = None
    db.commit()

    aggregate: dict[str, Any] = {"tools_ran": 0, "sources_checked": 0, "sources_total": 0, "findings": 0}
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
            db.add(
                m.Finding(
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
            )
        cc = result.coverage
        aggregate["tools_ran"] += 1
        aggregate["sources_checked"] += int(cc.get("sources_checked", 0))
        aggregate["sources_total"] += int(cc.get("sources_total", 0))
        aggregate["findings"] += len(result.findings)
        db.commit()

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
        scan.error = "no OSINT source returned data (network disabled or nothing found)"
    db.commit()
    db.refresh(scan)
    return scan