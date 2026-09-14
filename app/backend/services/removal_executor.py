"""Removal executor (Phase 16, slice 6) — human-gated, honest, escalating.

Deterministic rule set (never fabricated):

  - login-gated channels (account_delete, email, manual) -> `requires_manual`
    with the official removal URL + DRAFT. No credentials, no auto-send.
  - `anonymous_form` channels -> an automated attempt ONLY when a machine-
    submittable submitter profile is supplied (production default: none for
    today's curated registry, so those resolve to requires_manual with the
    official URL).
  - after any attempt, a re-verification MUST run: `removed` is recorded ONLY
    when the verifier reports the exposed URL is absent. A network error is
    `unknown` and is never treated as removal.
  - escalation: attempts retry up to `max_attempts`, then `requires_manual`.

The endpoint that calls this IS the human approval gate. Every transition is
audit-logged.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backend import models as m
from app.backend.models import _utcnow
from app.backend.services.removal_registry import (
    removal_channel_for,
    removal_url_for,
)

MAX_ATTEMPTS = 3
LOGIN_GATED_CHANNELS = frozenset({"account_delete", "email", "manual"})

Submitter = Callable[[str], dict[str, Any]]              # removal_url -> {"ok": bool, ...}
Verifier = Callable[[str], str]                           # url -> "absent" | "present" | "unknown"


def default_verifier(
    *,
    timeout: float = 10.0,
    session_factory: Callable[[], Any] | None = None,
) -> Verifier:
    """HEAD the exposed URL; 404/410/410-like => absent, else present, error => unknown."""

    def _verify(url: str) -> str:
        import httpx

        try:
            with (session_factory() if session_factory else httpx.Client(timeout=timeout)) as http:
                resp = http.head(url, follow_redirects=False)
            if resp.status_code in (404, 410, 451):
                return "absent"
            return "present"
        except Exception:  # noqa: BLE001 — network error is never a removal verdict
            return "unknown"

    return _verify


def start_removal(
    db: Session,
    action_id: int,
    *,
    submitter: Submitter | None = None,
    verifier: Verifier | None = None,
    max_attempts: int = MAX_ATTEMPTS,
) -> m.ActionExecution | None:
    """Run the removal ladder for one action. Returns the final execution row."""
    action = db.get(m.PrivacyAction, action_id)
    if action is None or action.status not in ("pending", "approved", "completed"):
        return None

    finding_url = action.finding.url if action.finding is not None else None
    channel = removal_channel_for(finding_url)
    removal_url = removal_url_for(finding_url)
    target = removal_url or finding_url

    _audit(db, action, "removal_start",
           f"remove requested by human for #{action.finding_id} url={finding_url}")
    db.commit()

    last: m.ActionExecution | None = None
    login_gated = channel in LOGIN_GATED_CHANNELS

    for attempt in range(1, max_attempts + 1):
        if login_gated:
            ex = _make_execution(db, action, attempt, channel, target, "requires_manual",
                                 note=(
                                     f"No credentials are ever used; complete the removal via the "
                                     f"official page ({removal_url or 'actions page'}) from the action's DRAFT."
                                 ))
            _audit(db, action, "requires_manual",
                   f"login-gated channel '{channel}'; official URL: {removal_url}")
            db.commit()
            last = ex
            break

        if submitter is None:
            # No reliable machine-submittable profile for this channel today.
            ex = _make_execution(db, action, attempt, channel, target, "requires_manual",
                                 note=(
                                     f"No machine-submittable removal profile is curated for "
                                     f"'{channel}'; use the official opt-out page ({removal_url}) manually."
                                 ))
            _audit(db, action, "requires_manual",
                   f"channel '{channel}' has no automated profile; official URL: {removal_url}")
            db.commit()
            last = ex
            break

        ex = _make_execution(db, action, attempt, channel, target, "submitted", note="attempt queued")
        result = submitter(target)
        ex.submitted_at = _utcnow()
        _audit(db, action, "submitted",
               f"attempt {attempt} returned {result}")
        db.commit()

        # Re-run verification after each attempt — the confirmation is real or it isn't.
        check = (verifier or default_verifier())(finding_url or target)
        ex.verified_at = _utcnow()
        ex.verification_detail = check
        if check == "absent":
            ex.status = "removed"
            action.status = "completed"
            _audit(db, action, "removed", f"verified absent after attempt {attempt}")
            db.commit()
            last = ex
            break
        if not result.get("ok"):
            ex.status = "failed"
            ex.note = f"attempt {attempt} failed: {result.get('detail', 'unknown')}"
            _audit(db, action, "failed", ex.note)
        else:
            ex.status = "still_present"
            ex.note = f"still present after attempt {attempt}; escalating"
            _audit(db, action, "still_present", ex.note)
        db.commit()
        last = ex

    # Ladder exhausted without removal.
    if last is not None and last.status in ("submitted", "still_present", "failed"):
        last.status = "requires_manual"
        last.note = (
            f"Automatic attempts exhausted after {max_attempts}; continue manually via the "
            f"official page {removal_url or '(none on file)'}."
        )
        _audit(db, action, "requires_manual", last.note)
        db.commit()
    return last


def _make_execution(
    db: Session,
    action: m.PrivacyAction,
    attempt: int,
    channel: str,
    target: str | None,
    status: str,
    *,
    note: str | None = None,
) -> m.ActionExecution:
    ex = m.ActionExecution(
        action_id=action.id,
        attempt=attempt,
        status=status,
        channel=channel,
        target_url=target,
        note=note,
    )
    db.add(ex)
    db.flush()
    return ex


def _audit(db: Session, action: m.PrivacyAction, action_code: str, detail: str) -> None:
    db.add(m.AuditLog(actor="user", action=action_code, entity_type="action",
                      entity_id=action.id, detail=detail))


def latest_execution(db: Session, action_id: int) -> m.ActionExecution | None:
    row = db.execute(
        select(m.ActionExecution)
        .where(m.ActionExecution.action_id == action_id)
        .order_by(m.ActionExecution.attempt.desc(), m.ActionExecution.id.desc())
    ).scalars().first()
    if row is not None:
        db.refresh(row)
    return row


def execution_summary(ex: m.ActionExecution | None) -> dict[str, Any] | None:
    if ex is None:
        return None
    return {
        "attempt": ex.attempt,
        "status": ex.status,
        "channel": ex.channel,
        "targetUrl": ex.target_url,
        "verifiedAt": ex.verified_at.isoformat() if ex.verified_at else None,
        "verificationDetail": ex.verification_detail,
        "note": ex.note,
    }