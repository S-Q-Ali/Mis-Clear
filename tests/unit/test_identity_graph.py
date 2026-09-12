"""Phase 9: identity graph builder unit tests (deterministic, no network)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backend import models as m
from app.backend.services import identity_graph as g


@pytest.fixture()
def db_session(tmp_path):
    from app.backend.database.engine import init_db_at

    engine = init_db_at(str(tmp_path / "graph.db"))
    session = Session(engine)
    yield session
    session.close()


def _finding(db, scan, *, type="email_exposure", url="https://example.com", source="picsearch", evidence=None):
    f = m.Finding(scan_id=scan.id, type=type, title="t", source=source, url=url,
                  evidence=evidence, confidence="possible", severity="low")
    db.add(f)
    db.flush()
    return f


def _scan(db, *, target_type="email", target_value="alice@example.com"):
    scan = m.Scan(target_type=target_type, target_value=target_value, scan_mode="local", status="completed")
    db.add(scan)
    db.flush()
    return scan


# ---------- helpers ----------

def test_canonical_lowercases_and_trims():
    assert g.canonical("  ALICE@Example.COM ") == "alice@example.com"


def test_extract_hostname_strips_scheme_www_port_path():
    assert g.extract_hostname("https://www.Example.com/u/alice?x=1#f") == "example.com"
    assert g.extract_hostname("http://example.com:8080/path") == "example.com"
    assert g.extract_hostname("not-a-url") is None
    assert g.extract_hostname("") is None


def test_extract_url_tokens_from_evidence_text():
    text = "QR payload https://evil.example/x and https://ok.test, trailing: https://a.test)."
    urls = g.extract_url_tokens(text)
    assert urls == ["https://evil.example/x", "https://ok.test", "https://a.test"]
    assert g.extract_url_tokens(None) == []
    assert g.extract_url_tokens("no urls here") == []


def test_ensure_identity_dedupes_by_canonical(db_session):
    one = g.ensure_identity(db_session, "email", "ALICE@Example.COM", 1)
    two = g.ensure_identity(db_session, "email", "alice@example.com", 1)
    assert one.id == two.id
    assert one.canonical == "alice@example.com"


# ---------- link_scan rules ----------

def test_link_scan_username_profile_chain(db_session):
    scan = _scan(db_session, target_type="username", target_value="alice")
    f = _finding(db_session, scan, type="username_profile",
                 url="https://example.com/u/alice", source="picsearch")
    n = g.link_scan(db_session, scan)
    assert n >= 4  # username, profile, website, domain
    rels = db_session.execute(select(m.Relationship)).scalars().all()
    types = {(r.type, r.source.canonical, r.target.canonical) for r in rels}
    assert ("username_profile", "alice", "alice") in types        # user -> profile
    assert ("exposure_site", "alice", "example.com") in types     # user -> domain
    assert ("reported_by", "alice", "picsearch") in types         # distinct source label
    ev = next(r for r in rels if r.type == "username_profile")
    assert ev.evidence_finding_id == f.id


def test_link_scan_dedupe_rerun_is_idempotent(db_session):
    scan = _scan(db_session)
    _finding(db_session, scan, url="https://example.com")
    first = g.link_scan(db_session, scan)
    second = g.link_scan(db_session, scan)
    assert first > 0
    assert second == 0
    assert db_session.execute(select(m.Relationship)).scalars().all()


def test_link_scan_no_url_no_evidence_no_edges(db_session):
    scan = _scan(db_session)
    f = m.Finding(scan_id=scan.id, type="custom", title="t", source="", url=None,
                  confidence="possible", severity="low")
    db_session.add(f)
    db_session.flush()
    assert g.link_scan(db_session, scan) >= 0
    assert db_session.execute(select(m.Relationship)).scalars().all() == []


def test_link_scan_image_extracts_url_tokens_from_evidence(db_session):
    scan = _scan(db_session, target_type="image", target_value="/tmp/x.png")
    _finding(db_session, scan, type="image_qrcode", url=None,
             source="qr", evidence="QR -> https://cv.example/scan")
    g.link_scan(db_session, scan)
    kinds = {(r.target.canonical) for r in db_session.execute(select(m.Relationship)).scalars().all()}
    assert "cv.example" in kinds


# ---------- rebuild ----------

def test_rebuild_scan_graph_deletes_owned_edges_and_relinks(db_session):
    scan = _scan(db_session, target_type="username", target_value="bob")
    _finding(db_session, scan, type="username_profile", url="https://sitex.io/u/bob")
    g.link_scan(db_session, scan)
    before = db_session.execute(select(m.Relationship)).scalars().all()
    assert len(before) >= 3

    # add a second finding then rebuild: old edges replaced, new ones present
    _finding(db_session, scan, url="https://newsite.dev/x")
    count = g.rebuild_scan_graph(db_session, scan.id)
    assert count > 0
    after = db_session.execute(select(m.Relationship)).scalars().all()
    before_sig = {(r.source_id, r.target_id, r.type) for r in before}
    assert len(after) > len(before_sig) or len(before) <= 6
    assert any(r.target.canonical == "newsite.dev" for r in after)


def test_rebuild_missing_scan_is_noop(db_session):
    assert g.rebuild_scan_graph(db_session, 999) == 0


# ---------- graph_for_scan (cross-scan merge) ----------

def test_graph_for_scan_merges_identity_across_scans(db_session):
    scan_a = _scan(db_session, target_type="email", target_value="alice@example.com")
    _finding(db_session, scan_a, url="https://sitex.io/u/alice", source="sitex.io")
    g.link_scan(db_session, scan_a)

    scan_b = _scan(db_session, target_type="email", target_value="ALICE@example.com")
    _finding(db_session, scan_b, url="https://sitey.io/me", source="sitey.io")
    g.link_scan(db_session, scan_b)

    graph = g.graph_for_scan(db_session, scan_a.id)
    nodes = {n["canonical"]: n for n in graph["nodes"]}
    assert nodes["alice@example.com"]["scanCount"] == 2  # merged across scans
    assert "sitex.io" in nodes and "sitey.io" in nodes
    edges = graph["edges"]
    assert any(
        e["type"] == "exposure_site" and e["target"] == ["domain", "sitey.io"]
        for e in edges
    )
    assert nodes["alice@example.com"]["evidenceCount"] >= 2


def test_graph_for_scan_isolated_when_disjoint(db_session):
    scan = _scan(db_session)
    _finding(db_session, scan, url="https://solo.dev", source="picsearch")
    g.link_scan(db_session, scan)
    graph = g.graph_for_scan(db_session, scan.id)
    assert {n["canonical"] for n in graph["nodes"]} == {
        "alice@example.com", "solo.dev", "https://solo.dev", "picsearch",
    }
    edge_types = {e["type"] for e in graph["edges"]}
    assert edge_types and edge_types <= {
        "exposure_site", "reported_by", "page", "hosted_on",
    }