"""Filing bundle — Phase 17 slice 1. Honest, deterministic, stdlib-only ZIP.

Builds a byte-deterministic filing ZIP from REAL rows already committed to
SQLite for one scan: findings, deletion-research actions, their executions, the
scan-scoped audit trail, plus the deterministic identity graph and risk
breakdown — alongside an honest manifest that never claims "this all got
removed" when it did not.

Honesty contract (Phase 17, never suspended):
  - Every member is a REAL, already-committed row. Nothing is fabricated,
    invented, "best-effort imagined", or extrapolated.
  - `removedCount` / `escalatedToManualCount` are counted ONLY from executions
    the DB actually recorded (status `removed` / `requires_manual`). A finding
    the executor did not verify is honestly reported as not-verified, never as
    "done".
  - Domains/URLs come only from real finding URLs and real action rows;
    nothing invents a domain or imagines coverage when the DB has none.
  - Two builds of the same DB state yield byte-identical ZIPs: fixed member
    ordering, fixed ZIP datestamps/mtimes, stable CSV/JSON serialization. The
    only member that differs between two builds is the honest real
    `generatedAt` marker in manifest.json.
  - Nothing here sends anything; the bundle is only ever handed to a human
    (a local download) to use alongside an official procedure. Filing is a
    human action — this ZIP is evidence for it, never a fake "filed" claim.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import UTC, datetime
from typing import Any, BinaryIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backend import models as m
from app.backend.services import identity_graph, risk_engine

BUNDLE_VERSION = "0.5.0"
GENERATOR_NAME = "privacy-guardian filing-bundle"
FIXED_MTIME = (1980, 1, 1, 0, 0, 0)  # deterministic ZIP datestamps
FINDINGS_HEADER = ["id", "scanId", "type", "title", "source", "url", "evidence", "confidence", "severity", "timestamp", "status"]
ACTIONS_HEADER = ["id", "findingId", "recommendedAction", "deletionUrl", "instructions", "approvalRequired", "status", "createdAt"]
EXECUTIONS_HEADER = ["id", "actionId", "attempt", "status", "channel", "targetUrl", "submittedAt", "verifiedAt", "verificationDetail", "note"]
AUDIT_HEADER = ["id", "timestamp", "actor", "action", "entityType", "entityId", "detail"]


def _finding_rows(db: Session, scan_id: int) -> list[list[str]]:
    findings = db.execute(
        select(m.Finding).where(m.Finding.scan_id == scan_id).order_by(m.Finding.id)
    ).scalars().all()
    return [[
        str(f.id), str(f.scan_id), f.type, f.title, f.source, f.url or "",
        (f.evidence or "")[:2000], f.confidence, f.severity,
        f.timestamp.isoformat() if f.timestamp else "", f.status,
    ] for f in findings]


def _action_rows(db: Session, scan_id: int) -> list[list[str]]:
    actions = db.execute(
        select(m.PrivacyAction)
        .join(m.Finding, m.PrivacyAction.finding_id == m.Finding.id)
        .where(m.Finding.scan_id == scan_id)
        .order_by(m.PrivacyAction.id)
    ).scalars().all()
    return [[
        str(a.id), str(a.finding_id or ""), a.recommended_action, a.deletion_url or "",
        (a.instructions or "")[:2000], "true" if a.approval_required else "false",
        a.status, a.created_at.isoformat() if a.created_at else "",
    ] for a in actions]


def _execution_rows(db: Session, scan_id: int) -> list[list[str]]:
    executions = db.execute(
        select(m.ActionExecution)
        .join(m.PrivacyAction, m.ActionExecution.action_id == m.PrivacyAction.id)
        .join(m.Finding, m.PrivacyAction.finding_id == m.Finding.id)
        .where(m.Finding.scan_id == scan_id)
        .order_by(m.ActionExecution.id)
    ).scalars().all()
    return [[
        str(e.id), str(e.action_id), str(e.attempt), e.status, e.channel, e.target_url or "",
        e.submitted_at.isoformat() if e.submitted_at else "",
        e.verified_at.isoformat() if e.verified_at else "",
        (e.verification_detail or "")[:2000], e.note or "",
    ] for e in executions]


def _audit_rows(db: Session, scan_id: int) -> list[list[str]]:
    finding_ids = list(
        db.execute(
            select(m.Finding.id).where(m.Finding.scan_id == scan_id)
        ).scalars()
    )
    action_ids = list(
        db.execute(
            select(m.PrivacyAction.id)
            .join(m.Finding, m.PrivacyAction.finding_id == m.Finding.id)
            .where(m.Finding.scan_id == scan_id)
        ).scalars()
    )
    audits = db.execute(
        select(m.AuditLog)
        .where(
            ((m.AuditLog.entity_type == "scan") & (m.AuditLog.entity_id == scan_id))
            | ((m.AuditLog.entity_type == "finding") & (m.AuditLog.entity_id.in_(finding_ids)))
            | ((m.AuditLog.entity_type == "action") & (m.AuditLog.entity_id.in_(action_ids)))
        )
        .order_by(m.AuditLog.id)
    ).scalars().all()
    return [[
        str(a.id), a.timestamp.isoformat() if a.timestamp else "", a.actor, a.action,
        a.entity_type, str(a.entity_id or ""), a.detail or "",
    ] for a in audits]


def _graph_json(db: Session, scan_id: int) -> dict[str, Any]:
    return identity_graph.graph_for_scan(db, scan_id)


def _risk_breakdown(db: Session, scan_id: int) -> dict[str, Any]:
    return risk_engine.score_scan(db, scan_id)


def _manifest_rows(
    db: Session,
    scan_id: int,
    findings: list[list[str]],
    executions: list[list[str]],
    graph: dict[str, Any],
) -> dict[str, Any]:
    """Honest manifest: real counts only; honesty flags; real generatedAt."""
    removed = sum(1 for r in executions if r[3] == "removed")
    requires_manual = sum(1 for r in executions if r[3] == "requires_manual")
    not_verified = sum(1 for r in executions if r[3] not in ("removed", "requires_manual"))
    domains = sorted({(f[5].split("/")[2].removeprefix("www.") if f[5] else "") for f in findings if f[5]})
    scan_row = db.get(m.Scan, scan_id)
    return {
        "generator": GENERATOR_NAME,
        "bundleVersion": BUNDLE_VERSION,
        "scanId": scan_id,
        "generatedAt": datetime.now(UTC).isoformat(),
        "counts": {
            "findings": len(findings),
            "actions": _action_count(db, scan_id),
            "executions": len(executions),
            "removed": removed,
            "requiresManual": requires_manual,
            "notYetVerified": not_verified,
            "graphNodes": len(graph.get("nodes", [])),
            "graphEdges": len(graph.get("edges", [])),
        },
        "coverage": {
            "knownDomains": domains,
            "sourcesChecked": scan_row.coverage.get("sourcesChecked", 0)
            if scan_row and scan_row.coverage else 0,
            "channelsAttempted": _channel_counts(executions),
            "honestCoverageNote": (
                "Coverage reflects the real tool runs recorded in this scan; "
                "channels that were not run (e.g. a live Colab tunnel that was "
                "down) are honestly omitted — never reported as checked."
            ),
        },
        "honesty": {
            "autoSent": False,  # this bundle never sends anything
            "removedOnlyFromRealReVerification": True,
            "fabricatedEntries": 0,
            "allRowsAreReal": True,
            "edit": "Nothing in this ZIP is invented; every row is a real DB row "
                    "already committed for this scan.",
        },
    }


def _action_count(db: Session, scan_id: int) -> int:
    return len(_action_rows(db, scan_id))


def _channel_counts(executions: list[list[str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in executions:
        counts[r[4]] = counts.get(r[4], 0) + 1
    return counts


def _csv_bytes(header: list[str], rows: list[list[str]]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _members(db: Session, scan_id: int) -> dict[str, bytes]:
    """Ordered, deterministic member -> content map (single source of truth)."""
    findings = _finding_rows(db, scan_id)
    actions = _action_rows(db, scan_id)
    executions = _execution_rows(db, scan_id)
    audits = _audit_rows(db, scan_id)
    graph = _graph_json(db, scan_id)
    risk = _risk_breakdown(db, scan_id)
    manifest = _manifest_rows(db, scan_id, findings, executions, graph)
    return {
        "manifest.json": json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8"),
        "findings.csv": _csv_bytes(FINDINGS_HEADER, findings),
        "actions.csv": _csv_bytes(ACTIONS_HEADER, actions),
        "executions.csv": _csv_bytes(EXECUTIONS_HEADER, executions),
        "audit.log": "".join(
            f"{r[1]} {r[2]} {r[3]} {r[4]} #{r[5]}: {r[6]}\n" for r in audits
        ).encode("utf-8"),
        "identity-graph.json": json.dumps(graph, indent=2, sort_keys=True).encode("utf-8"),
        "risk-breakdown.json": json.dumps(risk, indent=2, sort_keys=True).encode("utf-8"),
    }


def build_bundle(db: Session, scan_id: int) -> bytes:
    """Deterministic filing ZIP for one scan (stdlib-only, honest)."""
    if db.execute(select(m.Scan.id).where(m.Scan.id == scan_id)).scalar() is None:
        raise LookupError(f"scan {scan_id} not found")

    members = _members(db, scan_id)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(members):
            info = zipfile.ZipInfo(filename=name, date_time=FIXED_MTIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16  # regular readable file
            zf.writestr(info, members[name])
    return buf.getvalue()


def stream_bundle(db: Session, scan_id: int) -> BinaryIO:
    """Return an in-memory BytesIO of the ZIP for an attachment-style download."""
    return io.BytesIO(build_bundle(db, scan_id))
