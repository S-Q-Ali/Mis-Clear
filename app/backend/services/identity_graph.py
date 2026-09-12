"""Identity graph builder (Phase 9, master plan §9) — deterministic only.

Builds `Relationship` edges between identities from scan findings using fixed
rules (no AI). Node kinds: email | username | profile | domain | website |
image | source | custom. `canonical` (lowercased value) is the merge key across
scans: graph_for_scan collapses identities by (kind, canonical).

The graph is derived data — rebuildable at any time, never the source of truth.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backend import models as m

_URL_TOKEN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_SCHEME_SLASH = "://"


def canonical(value: str) -> str:
    """Merge key for identities — dumb and deterministic (lowercase/trim)."""
    return (value or "").strip().lower()


def extract_hostname(url: str) -> str | None:
    """Hostname from a URL, without scheme, www, port, or path."""
    if not url or _SCHEME_SLASH not in url:
        return None
    host = urlparse(url).hostname
    if not host:
        return None
    host = host.removeprefix("www.")
    return host.strip().lower() or None


def extract_url_tokens(text: str | None) -> list[str]:
    """Ordered unique URL tokens found in arbitrary evidence text."""
    if not text:
        return []
    seen = set()
    out = []
    for raw in _URL_TOKEN.findall(text):
        url = raw.rstrip(".,);]}")
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def ensure_identity(db: Session, kind: str, value: str, scan_id: int) -> m.Identity:
    """Get-or-create an identity by (kind, canonical). Deterministic merge key."""
    key = canonical(value)
    row = db.execute(
        select(m.Identity).where(m.Identity.kind == kind, m.Identity.canonical == key).limit(1)
    ).scalar_one_or_none()
    if row is not None:
        return row
    row = m.Identity(kind=kind, value=value, canonical=key, scan_id=scan_id)
    db.add(row)
    db.flush()
    return row


def _link(pairs: list[tuple[m.Identity, m.Identity, str, m.Finding | None]], db: Session) -> int:
    """Persist distinct (source, target, type) edges. Returns row count created."""
    created = 0
    for source, target, rel_type, finding in pairs:
        if source.id == target.id:
            continue
        exists = db.execute(
            select(m.Relationship).where(
                m.Relationship.source_id == source.id,
                m.Relationship.target_id == target.id,
                m.Relationship.type == rel_type,
            ).limit(1)
        ).scalar_one_or_none()
        if exists is not None:
            continue
        db.add(m.Relationship(
            source_id=source.id,
            target_id=target.id,
            type=rel_type,
            evidence_finding_id=finding.id if finding else None,
        ))
        created += 1
    db.flush()
    return created


def link_scan(db: Session, scan: m.Scan) -> int:
    """Deterministic rules: derive identity→identity relationships for one scan."""
    target = ensure_identity(
        db,
        kind=scan.target_type if scan.target_type in ("email", "username", "image") else "custom",
        value=scan.target_value,
        scan_id=scan.id,
    )
    pairs: list[tuple[m.Identity, m.Identity, str, m.Finding | None]] = []

    findings = db.execute(
        select(m.Finding).where(m.Finding.scan_id == scan.id)
    ).scalars().all()

    for finding in findings:
        url_source = extract_hostname(finding.url) if finding.url else None
        urls = extract_url_tokens(finding.evidence)

        # source label node (e.g. a search-engine/site label), distinct from hostname
        if finding.source and canonical(finding.source) not in (
            canonical(url_source) if url_source else "",
            target.canonical,
            "",
        ):
            src = ensure_identity(db, "source", finding.source, scan.id)
            pairs.append((target, src, "reported_by", finding))

        focus = []

        # profile node from username_profile findings (handle = last URL path segment)
        if finding.type == "username_profile" and finding.url:
            handle = None
            path = urlparse(finding.url).path.rstrip("/")
            if path:
                handle = path.rsplit("/", 1)[-1]
            if handle:
                handle = canonical(handle)
                profile = ensure_identity(db, "profile", handle, scan.id)
                pairs.append((target, profile, "username_profile", finding))
                focus.append(profile)

        # domain + website (page) nodes
        if url_source:
            domain = ensure_identity(db, "domain", url_source, scan.id)
            pairs.append((target, domain, "exposure_site", finding))
        finding_urls = []
        if finding.url:
            finding_urls.append(finding.url)
        for url in finding_urls + urls:
            host = extract_hostname(url)
            if not host:
                continue
            website = ensure_identity(db, "website", url.rstrip("/"), scan.id)
            hosts = ensure_identity(db, "domain", host, scan.id)
            if focus:
                for node in focus:
                    pairs.append((node, website, "profile_page", finding))
            else:
                pairs.append((target, website, "page", finding))
            pairs.append((website, hosts, "hosted_on", finding))

    return _link(pairs, db)


def rebuild_scan_graph(db: Session, scan_id: int) -> int:
    """Delete this scan's relationships (owned identities + finding evidence), relink."""
    scan_ids = db.execute(
        select(m.Identity.id).where(m.Identity.scan_id == scan_id)
    ).scalars().all()

    # delete Relationship rows also via evidence_finding_id belonging to this scan
    finding_ids = db.execute(
        select(m.Finding.id).where(m.Finding.scan_id == scan_id)
    ).scalars().all()

    edges = db.execute(select(m.Relationship)).scalars().all()
    doomed = [
        e for e in edges
        if e.source_id in scan_ids or e.target_id in scan_ids
        or (e.evidence_finding_id is not None and e.evidence_finding_id in finding_ids)
    ]
    for e in doomed:
        db.delete(e)
    db.flush()

    scan = db.get(m.Scan, scan_id)
    if scan is None:
        return 0
    return link_scan(db, scan)


def graph_for_scan(db: Session, scan_id: int, *, max_hops: int = 6) -> dict[str, Any]:
    """Connected component of relationships reachable from a scan's identities.

    Collapses identities across scans by (kind, canonical). Deterministic BFS.
    """
    identities = db.execute(
        select(m.Identity).where(m.Identity.scan_id == scan_id)
    ).scalars().all()
    if not identities:
        return {"nodes": [], "edges": []}

    key_of: dict[int, tuple[str, str]] = {}
    all_identities: dict[tuple[str, str], m.Identity] = {}
    identity_rows_by_key: dict[tuple[str, str], list[m.Identity]] = {}
    for row in db.execute(select(m.Identity)).scalars().all():
        key = (row.kind, row.canonical)
        key_of[row.id] = key
        identity_rows_by_key.setdefault(key, []).append(row)
        if key not in all_identities:
            all_identities[key] = row

    frontier = set()
    for row in identities:
        frontier.add(key_of[row.id])

    # edge adjacency over relationships, by merged keys
    edges_by_key: list[tuple[tuple[str, str], tuple[str, str], str, int | None]] = []
    for rel in db.execute(select(m.Relationship)).scalars().all():
        sk, tk = key_of.get(rel.source_id), key_of.get(rel.target_id)
        if sk is None or tk is None:
            continue
        edges_by_key.append((sk, tk, rel.type, rel.evidence_finding_id))

    reachable: set[tuple[str, str]] = set(frontier)
    changed = True
    hops = 0
    while changed and hops < max_hops:
        changed = False
        for sk, tk, _type, _ef in edges_by_key:
            if sk in reachable and tk not in reachable:
                reachable.add(tk)
                changed = True
            elif tk in reachable and sk not in reachable:
                reachable.add(sk)
                changed = True
        hops += 1

    nodes: list[dict[str, Any]] = []
    evidence_by_node: dict[tuple[str, str], int] = {}
    evidence_scans: dict[tuple[str, str], set[int]] = {}
    for sk, tk, _rel_type, ef in edges_by_key:
        if ef is not None:
            evidence_by_node[sk] = evidence_by_node.get(sk, 0) + 1
            evidence_by_node[tk] = evidence_by_node.get(tk, 0) + 1
            evidence_scans.setdefault(sk, set()).add(ef)
            evidence_scans.setdefault(tk, set()).add(ef)

    find_scans = {}
    if evidence_scans:
        ids = {i for s in evidence_scans.values() for i in s}
        for fid, sid in db.execute(
            select(m.Finding.id, m.Finding.scan_id).where(m.Finding.id.in_(ids))
        ).all():
            find_scans[fid] = sid

    nodes: list[dict[str, Any]] = []
    for key in reachable:
        row = all_identities[key]
        scan_ids = {r.scan_id for r in identity_rows_by_key.get(key, []) if r.scan_id is not None}
        for fid in evidence_scans.get(key, ()):
            if fid in find_scans:
                scan_ids.add(find_scans[fid])
        nodes.append({
            "id": list(key),
            "kind": key[0],
            "value": row.value,
            "canonical": key[1],
            "scanCount": len(scan_ids),
            "evidenceCount": evidence_by_node.get(key, 0),
        })

    edges: list[dict[str, Any]] = []
    for sk, tk, rel_type, ef in edges_by_key:
        if sk not in reachable or tk not in reachable:
            continue
        edges.append({
            "source": list(sk),
            "target": list(tk),
            "type": rel_type,
            "evidenceFindingId": ef,
        })

    return {"nodes": nodes, "edges": edges}