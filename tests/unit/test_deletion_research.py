"""Unit tests for deterministic deletion research (Phase 11, master plan §11)."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.backend import models as m
from app.backend.services.deletion_research import (
    DELETION_PROCEDURES,
    DRAFT_DISCLAIMER,
    approve_action,
    decline_action,
    find_procedure,
    is_candidate,
    prepare_request,
    research_finding,
    research_scan,
)


@pytest.fixture()
def session(tmp_path, monkeypatch):
    import app.backend.config as cfg
    import app.backend.database.engine as eng

    test_settings = cfg.Settings(database_path=str(tmp_path / "db.sqlite"),
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


def _finding(**kw):
    return m.Finding(
        scan_id=kw.get("scan_id", 1),
        type=kw.get("type", "email_exposure"),
        title=kw.get("title", "found"),
        source=kw.get("source", "leakdb"),
        url=kw.get("url", "https://reddit.com/u/alice"),
        evidence=kw.get("evidence", "synthetic"),
        confidence=kw.get("confidence", "confirmed"),
        severity=kw.get("severity", "high"),
        status=kw.get("status", "open"),
    )


def test_candidate_rule_deterministic():
    assert is_candidate(_finding())
    assert not is_candidate(_finding(confidence="possible"))
    assert not is_candidate(_finding(confidence="weak"))
    assert is_candidate(_finding(severity="medium"))
    assert not is_candidate(_finding(severity="informational"))
    assert not is_candidate(_finding(url=None))
    assert not is_candidate(_finding(status="reviewed"))


def test_curated_procedures_exist_with_real_urls():
    for domain, proc in DELETION_PROCEDURES.items():
        assert proc.organization
        assert proc.procedure_url and proc.procedure_url.startswith("https://")
        assert len(proc.steps) >= 1
        assert proc.domain == domain


def test_unknown_domain_honest_path():
    proc = find_procedure(_finding(url="https://obscure-xyz.test/u/jane"))
    assert proc.known is False
    assert proc.procedure_url is None
    assert proc.organization == "obscure-xyz.test"
    assert any("No curated procedure" in s for s in proc.steps)


def test_curated_domain_resolves_via_subdomain_and_scheme():
    proc = find_procedure(_finding(url="http://www.reddit.com/r/foo"))
    assert proc.known is True
    assert proc.organization == "Reddit, Inc."


def test_draft_request_is_deterministic_and_flagged():
    f = _finding(url="https://x.com/handle")
    proc = find_procedure(f)
    text1 = prepare_request(f, proc)
    text2 = prepare_request(f, proc)
    assert text1 == text2
    assert DRAFT_DISCLAIMER in text1
    assert "Do not send automatically" in text1
    assert "X Corp." in text1
    assert f.title in text1


def test_unknown_draft_prepends_honest_verdict():
    f = _finding(url="https://nope.test/x")
    proc = find_procedure(f)
    assert prepare_request(f, proc).startswith("Unknown service on file.")


def test_research_finding_creates_pending_gated_action(session):
    f = _finding()
    session.add(f)
    session.flush()
    action = research_finding(session, f)
    assert action.finding_id == f.id
    assert action.status == "pending"
    assert action.approval_required is True
    assert action.deletion_url == DELETION_PROCEDURES["reddit.com"].procedure_url
    assert "Reddit, Inc." in action.instructions
    assert DRAFT_DISCLAIMER in action.instructions
    assert action.evidence_reference == f"#{f.id}"


def test_research_finding_embeds_site_advisory(session):
    f = _finding(url="https://www.spokeo.com/u/alice")
    session.add(f)
    session.flush()
    action = research_finding(session, f)
    assert "Site advisory: data-broker" in action.instructions
    assert "recommended=False" in action.instructions


def test_research_finding_is_idempotent_and_no_clobber(session):
    f = _finding()
    session.add(f)
    session.flush()
    first = research_finding(session, f)
    session.flush()
    second = research_finding(session, f)
    assert first is second

    approve_action(session, first.id)
    session.flush()
    # after approval, re-research returns approved action unchanged
    again = research_finding(session, f)
    assert again.status == "approved"
    assert len(session.execute(select(m.PrivacyAction).where(
        m.PrivacyAction.finding_id == f.id)).scalars().all()) == 1


def test_research_scan_counts(session):
    scan = m.Scan(target_type="email", target_value="a@example.com", status="completed")
    session.add(scan)
    session.flush()
    session.add(_finding(scan_id=scan.id))                     # candidate
    session.add(_finding(scan_id=scan.id, confidence="weak"))  # not candidate
    session.add(_finding(scan_id=scan.id, url=None))           # not candidate
    session.flush()

    counts = research_scan(session, scan.id)
    assert counts == {"researchable": 3, "created": 1, "skipped": 0}
    # idempotent second pass
    assert research_scan(session, scan.id)["created"] == 0
    assert research_scan(session, scan.id)["skipped"] == 1


def test_approve_and_decline_transitions(session):
    f = _finding()
    session.add(f)
    session.flush()
    action = research_finding(session, f)
    session.flush()

    assert approve_action(session, action.id).status == "approved"
    assert approve_action(session, action.id).status == "approved"  # no re-transition
    assert action.approved_at is not None

    f2 = _finding(title="second")
    session.add(f2)
    session.flush()
    a2 = research_finding(session, f2)
    session.flush()
    assert decline_action(session, a2.id).status == "declined"
    session.flush()

    audits = session.execute(select(m.AuditLog)).scalars().all()
    assert len(audits) == 2
    assert all(log.actor == "user" for log in audits)


def test_transition_missing_action_returns_none(session):
    assert approve_action(session, 999999) is None
    assert decline_action(session, 999999) is None


def test_research_scan_missing_scan_returns_zero(session):
    assert research_scan(session, 424242) == {"researchable": 0, "created": 0, "skipped": 0}