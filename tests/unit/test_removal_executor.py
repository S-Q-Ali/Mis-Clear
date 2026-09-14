"""Slice 6: removal executor — human-gated, honest, escalating.

Contract (never fabricated):
  - login-gated channel (account_delete/email/manual) -> requires_manual, no submit
  - anonymous_form + no curated submitter -> requires_manual, official URL kept
  - anonymous_form + submitter ok + verifier "absent" -> removed (real confirmation)
  - submitter ok + verifier "present" -> escalation, then requires_manual after max
  - verifier "unknown" (network error) -> never treated as removed
  - result must be transparent to the API consumer via execution summary
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.backend import models as m
from app.backend.services.removal_executor import (
    MAX_ATTEMPTS,
    default_verifier,
    execution_summary,
    latest_execution,
    start_removal,
)


@pytest.fixture()
def session(tmp_path, monkeypatch):
    import app.backend.config as cfg
    import app.backend.database.engine as eng

    test_settings = cfg.Settings(database_path=str(tmp_path / "rdb.sqlite"),
                                 ollama_url="", colab_ollama_url="")
    monkeypatch.setattr(cfg, "settings", test_settings)
    monkeypatch.setattr(eng, "settings", test_settings)
    eng.engine = eng.build_engine(test_settings.database_path)
    eng.SessionLocal = sessionmaker(bind=eng.engine, autoflush=False, autocommit=False)
    eng.init_db()
    db = eng.SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _finding(url="https://spokeo.com/u/alice", **kw):
    return m.Finding(
        scan_id=kw.get("scan_id", 1),
        type=kw.get("type", "email_exposure"),
        title=kw.get("title", "found"),
        source=kw.get("source", "leakdb"),
        url=url,
        evidence=kw.get("evidence", "synthetic"),
        confidence=kw.get("confidence", "confirmed"),
        severity=kw.get("severity", "high"),
        status=kw.get("status", "open"),
    )


def _action(session, finding, status="pending"):
    session.add(finding)
    session.flush()
    a = m.PrivacyAction(finding_id=finding.id, recommended_action="remove",
                        approval_required=True, status=status)
    session.add(a)
    session.flush()
    return a


def test_login_gated_channel_requires_manual(session):
    a = _action(session, _finding(url="https://github.com/u/alice"))
    submitter = lambda url: {"ok": True}
    ex = start_removal(session, a.id, submitter=submitter,
                       verifier=lambda url: "present")
    assert ex.status == "requires_manual"
    assert ex.channel == "account_delete"
    assert ex.attempt == 1
    assert "No credentials" in (ex.note or "")
    assert "github.com" in (ex.target_url or "")


def test_anonymous_form_without_submitter_requires_manual(session):
    a = _action(session, _finding(url="https://spokeo.com/u/alice"))
    ex = start_removal(session, a.id, submitter=None, verifier=lambda url: "present")
    assert ex.status == "requires_manual"
    assert ex.channel == "anonymous_form"
    assert "machine-submittable" in (ex.note or "")


def test_anonymous_removed_only_after_absent_verification(session):
    a = _action(session, _finding(url="https://spokeo.com/u/alice"))
    calls = {"submit": 0, "verify": 0}

    def _submit(url):
        calls["submit"] += 1
        return {"ok": True}

    def _verify(url):
        calls["verify"] += 1
        return "absent"

    ex = start_removal(session, a.id, submitter=_submit, verifier=_verify)
    assert ex.status == "removed"
    assert ex.verification_detail == "absent"
    assert ex.verified_at is not None
    assert calls["submit"] == 1 and calls["verify"] >= 1
    db = session
    db.refresh(a)
    assert a.status == "completed"


def test_still_present_escalates_then_requires_manual(session):
    a = _action(session, _finding(url="https://spokeo.com/u/alice"))
    calls = {"verify": 0}

    def _submit(url):
        return {"ok": True}

    def _verify(url):
        calls["verify"] += 1
        return "present"

    ex = start_removal(session, a.id, submitter=_submit, verifier=_verify,
                       max_attempts=3)
    assert ex.status == "requires_manual"
    assert calls["verify"] == MAX_ATTEMPTS
    assert "exhausted" in (ex.note or "")
    rows = session.execute(select(m.ActionExecution)).scalars().all()
    assert any(r.status == "still_present" for r in rows)
    session.refresh(a)
    assert a.status == "pending"


def test_unknown_verification_never_removed(session):
    a = _action(session, _finding(url="https://spokeo.com/u/alice"))

    def _submit(url):
        return {"ok": True}

    ex = start_removal(session, a.id, submitter=_submit,
                       verifier=lambda url: "unknown", max_attempts=2)
    assert ex.status == "requires_manual"
    assert ex.verification_detail == "unknown"
    assert ex.status != "removed"


def test_failed_submission_escalates(session):
    a = _action(session, _finding(url="https://spokeo.com/u/alice"))
    submitter = lambda url: {"ok": False, "detail": "form 403"}
    ex = start_removal(session, a.id, submitter=submitter,
                       verifier=lambda url: "present", max_attempts=2)
    assert ex.status == "requires_manual"
    rows = session.execute(select(m.ActionExecution)).scalars().all()
    assert any(r.status == "failed" for r in rows)


def test_latest_execution_and_summary(session):
    a = _action(session, _finding(url="https://spokeo.com/u/alice"))
    start_removal(session, a.id, submitter=None, verifier=lambda url: "present")
    session.flush()
    ex = latest_execution(session, a.id)
    summary = execution_summary(ex)
    assert summary["status"] == "requires_manual"
    assert summary["channel"] == "anonymous_form"
    assert summary["targetUrl"]
    assert latest_execution(session, 999999) is None


def test_start_removal_guards_bad_action(session):
    assert start_removal(session, 99999) is None
    a = _action(session, _finding(), status="declined")
    assert start_removal(session, a.id) is None


def test_default_verifier_present_and_absent(monkeypatch):
    import httpx

    def _client(status_code):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code, headers={})

        return lambda: httpx.Client(transport=httpx.MockTransport(handler))

    verifier = default_verifier(session_factory=_client(404))
    assert verifier("https://x.test/a") == "absent"
    verifier2 = default_verifier(session_factory=_client(200))
    assert verifier2("https://x.test/b") == "present"


def test_removal_audited(session):
    a = _action(session, _finding(url="https://github.com/u/alice"))
    start_removal(session, a.id)
    logs = session.execute(select(m.AuditLog).where(m.AuditLog.entity_type == "action")
                           .order_by(m.AuditLog.id)).scalars().all()
    codes = [log.action for log in logs]
    assert "removal_start" in codes
    assert "requires_manual" in codes