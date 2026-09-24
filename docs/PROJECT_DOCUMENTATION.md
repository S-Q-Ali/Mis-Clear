# PROJECT_DOCUMENTATION

> Current product state (updates with every phase — documentation drift is a bug).

## Product

**Privacy Guardian** — local-first personal privacy/OSINT assistant. Laptop-hosted
UI + control plane, local evidence store, local Ollama AI (optional), optional
approved Google Colab GPU worker. Investigates email/username/image exposure,
correlates identities, scores risk, records evidence, and prepares human-approved
privacy actions.

The tool never claims "searched the entire internet"; it reports sources checked
and coverage gaps.

## Status by phase (2026-09-10)

| Phase | Title | Status |
|---|---|---|
| 0 | Environment audit | ✅ `docs/ENVIRONMENT_REPORT.md` |
| 1 | Bootstrap | ✅ structure, backend/frontend/test skeletons, health verified |
| 2 | Skills/Graphify | ✅ skills installed + `docs/SKILL_MATRIX.md` + project graph |
| 3 | Local AI / AI Router | ✅ `ModelRouter` code + tests (live Ollama deferred) |
| 4 | Database schema | ✅ 9 tables + versioned migrations; CRUD tests |
| 5 | Backend API | ✅ scans/findings/jobs/workers/reports + idempotency + error shape (28 tests) |
| 6 | OSINT adapters | ✅ email/username/web tools + orchestrator + run endpoint (53 tests) |
| 7 | Photo forensics | ✅ local pipeline: hashes/pHash/EXIF/QR + vision router stub + upload API (71 tests) |
| 8 | Colab worker | ✅ capability probe, handler registry, worker lifecycle, notebook + direct protocol (`/api/jobs/next`, `/result`), laptop dispatcher+API (105 tests) |
| 9 | Identity graph | ✅ deterministic link rules + cross-scan merge + graph API (121 tests) |
| 10 | Risk engine | ✅ deterministic, reproducible 0–100 scoring + risk API (143 tests) |
| 11 | Deletion research | ✅ official org/procedure + DRAFT requests + human approve/decline (160 tests) |
| 12 | Frontend UI | ✅ React UI over the control plane (build/lint clean, 162 tests) |
| 13 | Security | ✅ guardrails + 55-test battery + audits clean (217 tests) |
| 14 | Testing | ✅ E2E over real HTTP + failure/recovery battery + Colab worker protocol E2E (235 tests) |
| 15 | Audit | ✅ final audit + release notes (235 tests) |
| 16 | Removal | ✅ NSFW/photo‑nsfw async job + categorized takedown procedures + automated removal executor with human‑gate + re‑verify (see below) |
| 17 | Filing bundle | ✅ deterministic, honest, real‑rows‑only ZIP export of a scan (findings/actions/executions/audit/graph/risk + honesty manifest) |
| 15‑agent | Agentic self‑data investigator | ✅ chat‑driven personal‑data digger: strict‑JSON tool registry (`SPEC-agent-tools`), ReAct loop with allowlist + arg validation (`SPEC-agent-core`), SSE chat + 429 rate gate + redacted persisted conversations (`SPEC-agent-api`), React chat UI with streamed evidence + confirm buttons (`SPEC-agent-ui`), confirm‑gated removals → pending actions (no confirm → no action) (`SPEC-removal-flow`), PG_BREACH_API_URL k‑anonymity wiring (`SPEC-self-data`), injection/hybrid‑gate security suite (`SPEC-hardening`) — 406 tests |

## Current implementation

- **Backend** (`app/backend`): FastAPI app factory; REST control plane —
  `POST/GET /api/scans`, `/api/scans/{id}/findings`, `/api/scans/{id}/tool-runs`,
  `/api/scans/{id}/graph` (+ `/rebuild`), `/api/scans/{id}/risk`,
  `/api/scans/{id}/deletion-research`, `/api/actions` (+ `/approve`/`/decline`),
   `/api/scans/{id}/filing-bundle` (download-only),
  `/api/jobs` (+ `/dispatch`/`/poll`),
  `/api/workers`, `/api/reports/{scan_id}`; idempotent scan creation
   (`Idempotency-Key` header, dedupe + replay); consistent error envelope
   `{"error": {"code", "message", "details"}}` (422/404/409/500); contract-first
   camelCase Pydantic schemas (`app/backend/schemas.py`); SQLite engine
   (SQLAlchemy) with versioned migrations.
- **OSINT adapters** (`tools/`): stable `run(target) -> ToolResult` interface
  (`tools/base.py`); holehe/sherlock via site manifests (`tools/sitecheck.py`),
  manifests ship as real catalogs (username: sherlock-derived, https-only,
  NSFW/placeholder excluded; email: curated live-verified public services),
  web tools DNS-over-HTTPS (`tools/web/dns.py`), WHOIS/RDAP (`tools/web/whois.py`),
  DDG search (`tools/web/search.py`), GitHub (`tools/web/github.py`);
  `tools/registry.py` maps target types → adapters; `POST /api/scans/{id}/run`
  executes via `app/backend/services/scan_orchestrator.py` (persists ToolRun +
  Finding + Identity). All network in adapters is read-only public OSINT; a
  failure degrades to honest coverage, never a crash.
- **Photo forensics** (`tools/photo/`): local-first pipeline (Pillow + OpenCV
  headless + stdlib hashlib) — md5/sha256 (`hash.py`), perceptual d-hash
  (`phash.py`), EXIF/GPS (`exif.py`, untrusted metadata), QR decode (`qr.py`);
  `vision.py` is **Colab-first with a local-Ollama fallback**: local scans use a
  local vision backend only, hybrid scans transport the image (base64) through
  `app/backend/services/vision_transport.py` as a real `Job` and turn a worker's
  completed text into an `image_vision` finding; when a Colab job fails or
  interrupts, the adapter degrades gracefully to local Ollama before reporting
  `blocked` — blocked only when no backend exists at all (never fabricated
  findings). Configuring any Colab endpoint sets the effective default scan mode
  to `hybrid`. `POST
  /api/scans/{id}/image` uploads (validated magic bytes + size cap) to
  `data/uploads`, then the orchestrator persists an `Image` row (hashes/pHash)
  + findings for `targetType=image` scans.
- **Frontend** (`app/frontend`, Phase 12): React 19 + TypeScript SPA (Vite).
  Hash-free state-based sidebar navigation; typed API client (`src/api.ts`,
  `fetch('/api/*')` via Vite dev proxy → `127.0.0.1:8000`, FormData uploads);
  views: Dashboard (aggregate stats + worker status), Scans (create/list/run),
  Scan Detail (live polling while `running`; tabs for evidence findings, identity
  graph as a deterministic circular SVG with no layout library, photo analysis
  + upload, risk, deletion research), Actions (approve/decline privacy actions),
  Logs (audit trail, newest-first + filters), Workers, Settings (read-only,
  backed by `GET /api/settings`). Dark theme in `App.css`; oxlint clean
  (`react/only-export-components` kept at warn; compiler-only `set-state-in-effect`
  disabled for fetch-on-mount). No icon/router/UI libraries; no new npm deps.
- **UI support API** (Phase 12): `GET /api/logs` (audit log, newest-first,
  `entityType`/`actor` filters, paginated, `LogOut`) and read-only
  `GET /api/settings` (`SettingsOut`; POST/PUT → 405).
- **Protocol** (`colab/protocol.py`): versioned `JobRequest`/`JobResult` dataclasses.
- **Colab worker** (`colab/`): `capabilities.py` advertises GPU/CPU/models
  deterministically (`nvidia-smi` optional), `handlers.py` registers job types
  (`reasoning` → Ollama; vision/OCR/barcode/embeddings degrade honestly when
  unconfigured — never fabricated output), `worker.py` runs the master-plan §13
  lifecycle (`execute_job`: protocol → expiry → handler → temp cleanup →
  `data_deleted:true`; `run_worker_main` poll-proc-ack loop with reconnect),
  `dispatch.py` covers fetch/ack transport; runnable `privacy_guardian_worker.ipynb`
  (Colab: streamlit-free Ollama install via `ollama-linux-amd64.tar.zst` archive
  download + `zstd` decompress, 7 sections:
  configuration → Ollama install → model pulls → repo clone/deps → capability
  probe → dispatcher loop → optional Ollama tunnel).
  Direct worker protocol on the laptop (phase 8 follow-up): `GET /api/jobs/next`
  (oldest queued job pickup, marks `running`, expires stale items, audit
  `worker-pickup`) and `POST /api/jobs/{job_id}/result` (validates status,
  persists `completed|failed|interrupted` + `data_deleted`, audit
  `worker-result`).
  Laptop side: `app/backend/services/job_dispatcher.py` submits `JobRequest` to
  `colab_job_dispatcher_url` (empty → job stays queued with an honest
  "dispatcher not configured" error), polls results, expires late jobs as
  `interrupted` (never auto-completed); API `POST /api/jobs/{id}/dispatch` +
  `/poll`. End-to-end Colab transport is optional and offline-safe.
- **Identity graph** (`app/backend/services/identity_graph.py`, Phase 9):
  deterministic rule-based relationships (no AI) between email/username →
  profile → website → domain, `source` labels and URL tokens from evidence
  (e.g. QR payloads); `canonical = lower(value)` is the cross-scan merge key;
  `rebuild_scan_graph` idempotent; `graph_for_scan` returns the connected
  component (nodes: kind/value/canonical/scanCount/evidenceCount; edges with
  evidenceFindingId). Auto-linked best-effort after every scan run; API
  `GET /api/scans/{id}/graph` + `POST /api/scans/{id}/graph/rebuild`.
- **Risk engine** (`app/backend/services/risk_engine.py`, Phase 10): fully
  deterministic, reproducible 0–100 scores — no AI is ever allowed to compute
  the number. Six factors: severity, confidence, source reliability, data
  sensitivity, exposure age, correlation (peers of same type in the scan).
  `false_positive` is a hard gate (score 0). Partial weight overrides are
  rescaled to sum 1. `explain_risk` gives a deterministic, factor-attributing
  explanation (AI may only explain, never invent). API
  `GET /api/scans/{id}/risk` returns per-finding breakdown + aggregate
  (max + average), with scan-level correlation computed from independent
  confirmations.
- **Deletion research** (`app/backend/services/deletion_research.py`, Phase 11):
  for every confirmed/probable, meaningful-severity, URL-bearing open finding,
  produces a `PrivacyAction` (existing Phase 4 table, no migration): official
  organization, official procedure URL (curated registry of real, stable
  links), step-by-step instructions, and a deterministic DRAFT removal-request
  text explicitly marked "do not send automatically". Unknown domains take an
  honest `known=False` path (org label = hostname, no invented URL/steps).
  Actions start `pending` with `approvalRequired=True`; humans approve/decline
  via the API (audit-logged). **Nothing is ever sent by this module** — approval
  only marks a human-executed step. API
  `POST /api/scans/{id}/deletion-research`, `GET /api/actions[?scanId&status]`,
  `GET /api/actions/{id}`, `POST /api/actions/{id}/approve`|`/decline`.
- **Removal procedures** (`app/backend/services/removal_registry.py` +
  `takedown_procedures.py` + `draft_refinement.py`, Phase 16): curated
  `tools/site_manifests/removal.json` registry maps finding channels to official
  removal records (`find_removal_record`, `removal_channel_for`,
  `removal_url_for`); image findings map to the `adult` category via
  `procedure_for_finding` with honest opt-out/takedown templates; off-catalog
  categories get curated step templates (`CATEGORY_TEMPLATES`) and unknown
  domains take an explicit `known=False` path — never invented URLs or steps.
  `draft_refinement.py` refines an AI removal-request draft (wording only) with
  a deterministic `guard_urls` URL-integrity post-check that **discards any URL
  the source did not provide**; a refined removal draft is returned to the Colab
  worker. Nothing here auto-sends anything.
- **Removal executor** (`app/backend/services/removal_executor.py`, Phase 16,
  driven by the UI "Remove data" button): a per-finding/per-action removal
  attempt ladder (`start_removal`) that routes each channel to its removal
  procedure, keeps a default honest verifier (HEAD/URL re-check seeded from
  evidence), escalates via bounded channel attempts (`MAX_ATTEMPTS`), records
  `requires_manual` for login-gated/official-url-only flows (never fabricating
  a removal), re-verifies before reporting `removed` (404/absent), and appends
  the `removed` audit event only after real re-verification. Findings/actions
  already enriched with an `actionId`; every attempt is persisted to the
  `action_executions` table + audit log. API
  `POST /api/actions/{id}/remove` and `POST /api/findings/{id}/remove` →
  `RemovalOut` (findingId/actionId/status/execution); `GET /api/findings/{id}`
  returns `actionId`. Human-approval gate remains the UX contract — the button
  is click-to-launch research, removal itself stays approval-gated.
- **Security** (`app/backend/security/`, Phase 13): `url_safety.py` — SSRF/
  unsafe-URL guardrail (https-only, no userinfo, private/loopback/reserved IP
  literals + private hostname families rejected; manifest probe-URL authority
  check + host-consistency after `{target}` interpolation); `middleware.py` —
  security response headers (nosniff/DENY/no-referrer/CSP `default-src 'none'`,
  `no-store` on `/api`). Central evidence cap (2000 chars) in `tools/base.py`;
  upload decompression-bomb guard (`width*height` ≤ 50 MP). 55-test security
  battery in `tests/security/` (SSRF, unsafe URL, path traversal, upload
  hardening, command injection, prompt injection, malicious webpage,
  authorization, CORS/exposure, headers). Dep audits: pip-audit 0, npm audit 0.
- **Agentic self-data investigator** (`app/backend/services/agent/` +
  `app/backend/api/agent.py`, `SPEC-agent-*`): chat-driven dig for the user's
  OWN public data. `registry.py` wraps the deterministic adapters behind
  strict-JSON `ToolSpec`s (no shell/URL/exec tools exist); `breach.py` does
  k-anonymity breach checks (5-hex prefix, ephemeral, `PG_BREACH_API_URL`);
  `loop.py` runs the ReAct loop (allowlist + arg validation + step budget +
  `<untrusted>` result wrapping + deterministic removal proposals); `brain.py`
  routes to the Colab 27B tunnel → local Ollama → graceful block; SSE chat
  (`/api/agent/chat`) streams steps live and persists redacted audit
  conversations (V5 schema: `agent_conversations` + `agent_messages`); rate
  gate → 429. `removal_flow.py` + `POST /api/agent/confirm` create a `pending`
  PrivacyAction only after a per-item user confirm (no confirm → no action);
  reverse-image search and breach are gated behind `approveHybrid`. UI:
  `app/frontend/src/views/Agent.tsx` — streamed timeline, evidence links,
  approve/deny buttons, conversation history readback. Security suite
  `tests/security/test_agent_injection.py`.
- **Tests**: `tests/unit/*`, `tests/integration/*`, `tests/security/*`, `tests/e2e/*`,
   `tests/failure_recovery/*`; 406 pytest functions green (incl. the agent:
   tools/loop/removal unit + SSE chat/confirm integration + injection security
   suite; the 3 dispatch/settings env‑gated cases deselected)
- **E2E** (`tests/e2e/`, Phase 14): real uvicorn server on loopback + real SQLite
  DB + genuine HTTP via httpx — full investigation journey (create→run→
  findings→graph→risk→research→approve→logs), photo journey (multipart upload,
  real pipeline), Colab worker protocol (create→`/next` pickup→`/result`→
  persisted+audited; failure, empty, invalid-status cases), pagination/filters,
  report, headers over real sockets, and a server-restart test proving DB is the
  system of record.
- **Failure/recovery** (`tests/failure_recovery/`, Phase 14): Ollama retry
  (transient→recovers, persistent→clean `ModelUnavailableError`, no retry on
  success); dispatcher down-then-up recovery at submit and via poll. Found +
  fixed a real bug: `poll_job` compared naive (SQLite round-trip) `expires_at`
  against UTC-aware `now` → now normalized before compare.
- **Audit trail (Phase 15):** scan `run` events now logged (`action="run"`,
  detail `type:value run completed`) alongside create/approve/graph-rebuild —
  verified by integration test.
  + legacy (deferred) suite. Frontend: `tsc -b && vite build` and `oxlint` clean.
  Adapter tests run on fake transports (httpx.MockTransport)
  / synthetic images generated at test time — no live network, no real personal data.

## Architecture (landscape)

```
LAPTOP ── React+TS UI → FastAPI control plane → scan orchestrator
   → local agents/tools (email/username/web/photo/risk)
   → SQLite + evidence store → identity graph (deterministic relationships)
   → optional Colab job dispatcher (explicit approval only)
   ↔ UI support: /api/logs (audit trail) + /api/settings (read-only)
Colab = disposable GPU worker (vision/OCR/embedding), never system of record.
```

## Dependencies

- Backend: fastapi, uvicorn, pydantic, pydantic-settings, sqlalchemy, httpx, pillow, opencv-python-headless, python-multipart (managed via `uv`, `pyproject.toml`).
- Frontend: react, typescript, vite (Phase 12: real SPA; no extra runtime deps; oxlint for linting).
- AI: Ollama (Qwen-family local reasoning; Gemma/Qwen-VL vision), models configurable. Heavy vision/OCR → approved Colab worker (Phase 8).
- OSINT (Phase 6): holehe, sherlock, maigret, WHOIS/DNS, public search — behind stable adapters.
- Image (Phase 7): Pillow (EXIF/dhash), OpenCV headless (QR), stdlib hashlib; OCR/local vision dispatched to Colab worker.
- Colab transport (Phase 8): httpx (job submit/poll), `colab/*` worker package + notebook.

## Security posture (summary)

Local-only by default; hybrid/Colab requires explicit approval; no passwords stored
or requested; never fabricate evidence; all web content treated as untrusted data.
See `docs/SECURITY_MODEL.md` and `docs/THREAT_MODEL.md`.

## Known limitations

- Ollama not installed → AI features degrade gracefully to "unavailable".
- Local GPU (MX250 2 GB) is weak → heavy batches target approved Colab worker.
- No destructive action is one-click; user approval is mandatory.
- Coverage is honest: sources checked vs. sources unavailable are both reported.