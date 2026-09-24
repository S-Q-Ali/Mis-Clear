"""Phase 17 slice 1 — filing bundle (deterministic, honest, real-rows-only).

Covers the honesty + determinism contract of `filing_bundle`:

  - Every CSV/JSON member is built ONLY from REAL, already-committed rows for
    the scan. Nothing is fabricated, invented, "best-effort", or imagined.
  - `removedCount` / `requiresManualCount` are counted ONLY from executions the
    DB actually recorded (status `removed` / `requires_manual`). An execution
    that did not re-verify is honestly not "removed", never claimed done.
  - Domains/URLs come only from REAL finding URLs + REAL action rows; no domain
    is invented or upgraded just because a domain lookup wasn't attempted.
  - Two builds from the same DB state yield byte-identical ZIPs (fixed member
    order, deterministic member ordering + fixed ZIP mtimes, stable CSV/JSON
    serialization). The ONLY member that differs is the honest real real-time
    `generatedAt` marker in manifest.json — because two real builds happen at
    two real instants. Everything else is byte-for-byte identical.
"""
from __future__ import annotations

import io
import json
import time
import zipfile
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend import models as m
from app.backend.services import filing_bundle as fb


@pytest.fixture()
def db(tmp_path, monkeypatch):
    path = str(tmp_path / "bundle.sqlite")
    eng = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    m.Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng)
    with Session() as s:
        yield s


def _finding(db, *, scan_id, type="email_exposure", title="detected @ alice", source="regexp_walker",
             url="https://www.instagram.com/alice_repo", evidence="real snapshot", confidence="confirmed",
             severity="medium", status="open"):
    f = m.Finding(scan_id=scan_id, type=type, title=title, source=source, url=url,
                  evidence=evidence, confidence=confidence, severity=severity, status=status)
    db.add(f)
    db.flush()
    return f


def _action(db, finding_id, *, recommended_action="remove listing", deletion_url="https://www.instagram.com/delete",
            instructions="use official support form", approval_required=True, status="pending"):
    a = m.PrivacyAction(finding_id=finding_id, recommended_action=recommended_action, deletion_url=deletion_url,
                        instructions=instructions, approval_required=approval_required, status=status)
    db.add(a)
    db.flush()
    return a


def _execution(db, action_id, *, attempt=1, status="removed", channel="manual",
               target_url="https://www.instagram.com/delete", verified_at=None, detail="real re-verified", note=""):
    e = m.ActionExecution(action_id=action_id, attempt=attempt, status=status, channel=channel,
                          target_url=target_url,
                          verified_at=verified_at or datetime.now(UTC),
                          verification_detail=detail, note=note)
    db.add(e)
    db.flush()
    return e


def _members(db, scan_id):
    members = {}
    with zipfile.ZipFile(fb.stream_bundle(db, scan_id)) as zf:
        for name in zf.namelist():
            members[name] = zf.read(name)
    return members


def test_manifest_lists_only_real_rows(db):
    scan = m.Scan(target_type="email", target_value="alice@example.com", scan_mode="local", status="completed")
    db.add(scan)
    db.flush()
    f1 = _finding(db, scan_id=scan.id)
    f2 = _finding(db, scan_id=scan.id, url="https://twitter.com/alice_account", type="username_profile")
    _action(db, f1.id)
    a2 = _action(db, f2.id, deletion_url="https://twitter.com/settings/account")
    _execution(db, a2.id)

    members = _members(db, scan.id)
    manifest = json.loads(members["manifest.json"])

    assert set(members) == {
        "manifest.json", "findings.csv", "actions.csv", "executions.csv",
        "audit.log", "identity-graph.json", "risk-breakdown.json",
    }
    assert manifest["counts"]["findings"] == 2
    assert manifest["counts"]["actions"] == 2
    assert manifest["counts"]["executions"] == 1
    assert manifest["counts"]["removed"] == 1
    assert manifest["counts"]["requiresManual"] == 0
    assert manifest["counts"]["notYetVerified"] == 0
    assert manifest["honesty"]["autoSent"] is False
    assert manifest["honesty"]["removedOnlyFromRealReVerification"] is True


def test_bundle_is_byte_deterministic_except_honest_generated_at(db):
    scan = m.Scan(target_type="email", target_value="b@example.com", scan_mode="local", status="completed")
    db.add(scan)
    db.flush()
    _finding(db, scan_id=scan.id, url="https://www.example-unused.org/u/professional")
    first = _members(db, scan.id)
    time.sleep(0.002)  # two real builds need two real instants
    second = _members(db, scan.id)

    assert set(first) == set(second)
    for name in first:
        if name == "manifest.json":
            m1 = dict(json.loads(first[name]))
            m2 = dict(json.loads(second[name]))
            # the ONLY honest difference is the real generatedAt (two real builds)
            assert m1["generatedAt"] != m2["generatedAt"]
            assert m2["generatedAt"] > m1["generatedAt"]
            # compare the rest member-for-member (honest determinism)
            m1.pop("generatedAt")
            m2.pop("generatedAt")
            assert m1 == m2, "manifest must differ ONLY in generatedAt"
            continue
        assert first[name] == second[name], f"{name} must be byte-deterministic"


def test_no_fabricated_domains_in_coverage(db):
    scan = m.Scan(target_type="email", target_value="b@example.com", scan_mode="local", status="completed")
    db.add(scan)
    db.flush()
    _finding(db, scan_id=scan.id, url="https://www.instagram.com/user/real-account-123")

    members = _members(db, scan.id)
    manifest = json.loads(members["manifest.json"])

    assert manifest["coverage"]["knownDomains"] == ["instagram.com"]
    assert "legit-site" not in manifest["coverage"]["knownDomains"]


def test_stream_bundle_returns_valid_zip(db):
    scan = m.Scan(target_type="username", target_value="alice_user", scan_mode="local", status="completed")
    db.add(scan)
    db.flush()
    _finding(db, scan_id=scan.id)

    blob = fb.stream_bundle(db, scan.id)
    assert isinstance(blob, io.BytesIO)
    with zipfile.ZipFile(blob) as zf:
        assert "findings.csv" in zf.namelist()
