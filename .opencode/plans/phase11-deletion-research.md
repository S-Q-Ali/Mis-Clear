# Plan — Phase 11: Deletion Research (confirmed exposures → human-approved actions)

Controlling spec: MASTER_BUILD_INSTRUCTIONS.md §11 — for each confirmed public
exposure: identify official organization, find official privacy/delete
procedure, record URL, explain steps, prepare optional request, require
approval before sending anything.

## Design
- Reuse existing `PrivacyAction` table ("actions", Phase 4) — **no migration**.
  Flow: research ⇒ PrivacyAction(status=pending, approval_required=True) ⇒
  human endpoint approve/decline (audit-logged). **Nothing is ever sent** —
  approval marks a human-executed step; sending itself stays out of scope.
- `app/backend/services/deletion_research.py` — all deterministic, no AI:
  - `CANDIDATE_CONFIDENCE = {"confirmed","probable"}`, `CANDIDATE_SEVERITY =
    {"critical","high","medium"}`; candidate findings also need `url` and
    `status == "open"`.
  - Curated `DELETION_PROCEDURES`: well-known domains → organization,
    official procedure URL, concrete steps (static text). Unknown domain:
    `known=False`, org = hostname label, procedure_url None, steps = honest
    transparency text ("no curated procedure on file — verify against the
    domain's official support/safety pages"). Never fabricate a URL.
  - `identify_organization(finding)` / `find_procedure(finding)` /
    `prepare_request(finding, proc)` → deterministic draft removal-request
    text explicitly labeled DRAFT, must-not-send (interpolates title, source,
    reference, url).
  - `research_finding(db, finding)` → get-or-create action (skip if a
    non-pending action exists: never clobber approved/declined). Populates
    recommended_action, deletion_url, instructions (steps + draft), evidence_
    reference, approval_required=True, status="pending".
  - `research_scan(db, scan_id)` → research every candidate finding in the
    scan; returns counts. Missing scan → 0 actions, no error.
  - `approve_action(db, action_id, actor)` — pending→approved + approved_at +
    AuditLog; `decline_action` — pending→declined + AuditLog.
- API:
  - `POST /api/scans/{id}/deletion-research` → `DeletionResearchOut` (created,
    skipped, error counts; 404 missing scan).
  - `GET /api/actions` (optional `scanId`, paginated) + `GET /api/actions/{id}`
    + `POST /api/actions/{id}/approve` + `POST /api/actions/{id}/decline`.
  - Schemas: `PrivacyActionOut`, `DeletionResearchOut`.

## Slices
- A. `deletion_research.py` service + unit tests (candidate rule, curated vs
  unknown, draft template DRAFT anchor, idempotent get-or-create, no-clobber,
  approve/decline transitions, scan research counts) → commit.
- B. schemas + routers (scans.py research endpoint, new actions.py) + main.py
  registration + integration tests → commit.
- C. Docs (PROJECT_DOCUMENTATION/ARCHITECTURE/TOOL_MATRIX polish, SESSION_STATE)
  + full suite + push.

## Guardrails
- Synthetic fixtures only. No randomness. Never fabricate a deletion URL or
  org for unknown domains (honest `known=False` path). Approval gating is
  non-negotiable (master plan §1 + §11): no auto-send anywhere.