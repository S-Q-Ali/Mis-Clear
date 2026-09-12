# Plan — Phase 9: Identity Graph (deterministic, cross-scan merge)

Controlling spec: MASTER_BUILD_INSTRUCTIONS.md §9 (relationships between email,
username, profile, domain, website, image, finding, source). Graph is
**derived data** — built by deterministic rules (no AI), used for user-facing
investigation (UI rendering in Phase 12).

Existing schema (Phase 4) already has `Identity` + `Relationship` (source_id,
target_id, type, evidence_finding_id) but nothing populates it.
`scan_orchestrator` persists only ONE identity (the scan target) today.

## Design
- Node kinds (`Identity.kind`): `email | username | profile | domain | website |
  image | source | custom` — findings map to edge `evidence_finding_id`;
  "source" (finding.source label) becomes a `source` identity node.
- Canonical merge key: `(kind, canonical)` with `canonical = value.strip().lower()`.
  Cross-scan merge = connected component in Relationship space, then collapse.
- `app/backend/services/identity_graph.py`:
  - `canonical(value)`, `extract_hostname(url)` (strip scheme/www/port/path),
    `extract_url_tokens(text)` (regex for evidence text, e.g. QR payloads).
  - `ensure_identity(db, kind, value, scan_id)` — get-or-create by (kind, canonical).
  - `link_scan(db, scan)` — deterministic rules per finding:
    - target identity (scan.target_type) → `source` node (type `reported_by`) when
      finding.source differs from its URL hostname.
    - target → `domain` (type `exposure_site`) and/or `website` (page URL,
      type `page`) from finding.url and URL tokens in evidence.
    - `username_profile` findings → `profile` node (handle from URL path);
      edges target→profile (`username_profile`), profile→website→domain.
  - `rebuild_scan_graph(db, scan_id)` — delete relationships owned by the scan,
    re-run `link_scan` (idempotent).
  - `graph_for_scan(db, scan_id)` — connected component BFS over relationships,
    collapses identities by (kind, canonical) across scans →
    `{nodes: [{key,kind,value,canonical,scanCount,evidenceCount}], edges: [...]}`.
- API (scans.py):
  - `GET /api/scans/{id}/graph` → GraphOut (404 if scan missing).
  - `POST /api/scans/{id}/graph/rebuild` → rebuild + GraphOut + AuditLog.
- orchestrator: best-effort `link_scan(db, scan)` after completed (guarded).
- Schemas: `GraphNode`, `GraphEdge`, `GraphOut`.

## Slices (thin, verified + committed each)
- A. Service core rules (`link_scan`, `rebuild_scan_graph`) + unit tests → commit.
- B. `graph_for_scan` cross-scan component + unit tests → commit.
- C. Schemas + API endpoints + integration tests → commit.
- D. Orchestrator auto-link hook + tests → commit.
- E. Docs (PROJECT_DOCUMENTATION, ARCHITECTURE, TOOL_MATRIX note) + SESSION_STATE + full suite + commit + push.

## Guardrails
- Synthetic fixtures only; zero network in tests.
- Deterministic rules only — the AI never invents graph edges or scores.
- No schema migration needed (Phase 4 tables reused).