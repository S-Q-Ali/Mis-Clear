"""Idempotency guard for POST /api/scans.

The unique PK is the mechanism (atomic claim); request_hash guards against a
key reused with a different payload. Duplicates before a result is persisted →
409 (in-flight). Same payload + existing result → replay (200).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.backend import models as m


def request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class IdempotencyClaim:
    """Result of claiming an idempotency key for scan creation."""

    def __init__(self, disposition: str, scan: m.Scan | None = None) -> None:
        self.disposition = disposition  # "created" | "replay" | "conflict" | "mismatch" | "inflight"
        self.scan = scan


def claim(db: Session, key: str, payload: dict[str, Any]) -> IdempotencyClaim:
    """Atomically claim `key` for create-scan. Caller must commit afterwards."""
    rqhash = request_hash(payload)
    db.add(m.IdempotencyKey(key=key, request_hash=rqhash))
    db.flush()
    return IdempotencyClaim("created")  # key claimed under unique PK


def replay(db: Session, key: str, payload: dict[str, Any]) -> IdempotencyClaim:
    """Resolve when the claim collided: replay, mismatch, or in-flight conflict."""
    row = db.execute(select(m.IdempotencyKey).where(m.IdempotencyKey.key == key)).scalar_one_or_none()
    if row is None:
        return IdempotencyClaim("conflict")  # unreachable state safety
    if row.request_hash != request_hash(payload):
        return IdempotencyClaim("mismatch")
    scan = None
    if row.scan_id is not None:
        scan = db.get(m.Scan, row.scan_id)
    if scan is not None:
        return IdempotencyClaim("replay", scan)
    return IdempotencyClaim("inflight")