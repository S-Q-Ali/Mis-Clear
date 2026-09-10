"""Phase 4: schema migration + CRUD round-trips on an isolated temp DB."""

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backend import models as m
from app.backend.database.engine import init_db_at
from app.backend.database.migrations import current_version


def _fresh_session(tmp_path):
    db_path = tmp_path / "pg.db"
    engine = init_db_at(str(db_path))
    return engine, Session(engine)


def test_migrate_creates_schema_and_tracks_version(tmp_path):
    engine, _ = _fresh_session(tmp_path)
    assert current_version(engine) == 3
    with engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                sa.text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
    expected = {
        "scans", "identities", "relationships", "findings", "images",
        "actions", "jobs", "tool_runs", "audit_logs", "schema_versions",
        "idempotency_keys",
    }
    assert expected <= tables


def test_migrate_is_idempotent(tmp_path):
    db_path = tmp_path / "idem.db"
    init_db_at(str(db_path))
    init_db_at(str(db_path))  # second run must not raise
    engine = _fresh_session(tmp_path)[0]
    assert current_version(engine) == 3


def test_scan_gives_rise_to_findings_and_tool_runs(tmp_path):
    _, session = _fresh_session(tmp_path)
    scan = m.Scan(target_type="email", target_value="alice@example.com", scan_mode="local")
    session.add(scan)
    session.flush()

    session.add_all(
        [
            m.Finding(
                scan_id=scan.id, type="email_exposure", title="Public in breach dumps",
                source="synthetic-fixture", url="https://example.test/dump",
                evidence="seen in synthetic corpus", confidence="probable",
                severity="high", tool="fixture-tool",
            ),
            m.ToolRun(scan_id=scan.id, tool="fixture-tool", status="completed",
                      duration_ms=10, coverage="synthetic", findings_count=1),
            m.AuditLog(actor="tester", action="create", entity_type="scan", entity_id=scan.id),
        ]
    )
    session.commit()

    rows = session.execute(select(m.Finding)).scalars().all()
    assert len(rows) == 1 and rows[0].severity == "high" and rows[0].confidence == "probable"
    assert session.execute(select(m.ToolRun)).scalars().one().findings_count == 1
    assert session.execute(select(m.AuditLog)).scalars().one().action == "create"


def test_identity_graph_relationships(tmp_path):
    _, session = _fresh_session(tmp_path)
    email = m.Identity(kind="email", value="alice@example.com")
    profile = m.Identity(kind="profile", value="https://example.test/u/alice")
    session.add_all([email, profile])
    session.flush()
    session.add(m.Relationship(source_id=email.id, target_id=profile.id,
                               type="email->profile", evidence_finding_id=None))
    session.commit()

    session.expire_all()
    rels = session.execute(select(m.Relationship)).scalars().all()
    assert len(rels) == 1 and rels[0].type == "email->profile"
    assert rels[0].source.value == "alice@example.com"
    assert rels[0].target.value.endswith("/alice")


def test_image_and_action_rows(tmp_path):
    _, session = _fresh_session(tmp_path)
    scan = m.Scan(target_type="image", target_value="photo.jpg")
    session.add(scan)
    session.flush()
    session.add(
        m.Image(scan_id=scan.id, filename="photo.jpg", local_path="data/uploads/photo.jpg",
                md5="d41d8cd98f00b204e9800998ecf8427e",
                sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                phash="abcdef", exif={"lat": 40.0})
    )
    session.add(m.PrivacyAction(finding_id=None, recommended_action="Request deletion",
                                deletion_url="https://example.test/delete",
                                approval_required=True, status="pending"))
    session.commit()
    assert session.execute(select(m.Image)).scalars().one().exif["lat"] == 40.0
    assert session.execute(select(m.PrivacyAction)).scalars().one().status == "pending"


def test_job_records_protocol_roundtrip(tmp_path):
    _, session = _fresh_session(tmp_path)
    session.add(m.Job(job_id="11111111-2222-3333-4444-555555555555", job_type="vision_analysis",
                      protocol_version="1", status="queued"))
    session.commit()
    job = session.execute(select(m.Job)).scalars().one()
    assert job.protocol_version == "1" and job.status == "queued"