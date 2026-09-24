# ARCHITECTURE (current + target)

## Target

```
┌──────────────────────────────────────────────┐
│                 LAPTOP                        │
│  React + TypeScript UI                        │
│       ↓                                       │
│  FastAPI Control Plane (127.0.0.1)            │
│       ↓                                       │
│  Scan Orchestrator                            │
│       ↓                                       │
│  ┌──────────────────────────────────────────┐ │
│  │ Local Agents / Tools                     │ │
│  │ Email / Username / Web / Photo / Risk   │ │
│  └──────────────────────────────────────────┘ │
│       ↓                                       │
│  SQLite + Evidence Store                      │
│       ↓                                       │
│  Optional Colab Job Dispatcher                │
└──────────────────────┬───────────────────────┘
                       │ explicit approval
                       ▼
             GOOGLE COLAB (T4 GPU worker)
```

Colab is a **worker**, not the system of record. Laptop owns UI, DB, scan state,
evidence, config, reports, approvals. Colab is treated as a **temporary compute
runtime** (T4/L4/... = configuration change, not a rewrite).

## AI Router

Heavy AI never blocks the app. `ModelRouter` (`app/backend/services/model_router.py`):

```
                 AI ROUTER
                      │
          ┌───────────┴───────────┐
          │                       │
          ▼                       ▼
    LOCAL OLLAMA            COLAB OLLAMA (GPU tunnel)
    available?             approved AND available?
          │                       │
          └───────────┬───────────┘
                      ▼
                   Result
    none available → ModelUnavailableError (graceful task queue / shown as inactive)
```

- Priority: approved Colab → local → graceful failure.
- `strict_local` = LOCAL ONLY: Colab never used, regardless of approval.
- Zero-AI install is supported: router degrades without any Ollama.
- Colab AI worker is NOT a permanent server; it is a disposable runtime whose
  disappearance yields `interrupted`/inactive states, never wrong results.

## Current (Phase 5 realisation)

- `app/backend/main.py` — FastAPI `create_app()`; CORS restricted to local Vite origin;
  exception handlers (validation → 422, HTTP → consistent envelope); routers wired.
- `app/backend/config.py` — `Settings` (env prefix `PG_`, `.env` support).
- `app/backend/database/engine.py` — SQLite `engine`, `SessionLocal`, `init_db()`, `get_db()`.
- `app/backend/schemas.py` — contract-first Pydantic IO (camelCase JSON, snake_case ORM via
  alias mapping; `Paginated[T]` + `pagination_meta`, pageSize ≤ 100).
- `app/backend/errors.py` — single error envelope + handlers.
- `app/backend/api/{health,scans,findings,jobs,workers,reports,logs,settings}.py` —
  REST control plane (handlers: scans CRUD/findings/tool-runs, jobs CRUD, workers
  status/probe, reports aggregation, audit-log read, read-only settings). Jobs
  adds the direct worker protocol: `GET /api/jobs/next` (pickup, marks running,
  expires stale) and `POST /api/jobs/{job_id}/result` (persist JobResult).
- `app/backend/services/{model_router,idempotency}.py` — AI routing; idempotency keys
  (`idempotency_keys` table: atomic claim, replay/mismatch/in-flight resolution).
- `app/backend/models.py` + `database/migrations.py` — 9 tables + versioned migrations (v3).
- `app/backend/services/scan_orchestrator.py` — runs adapters for a scan, persists
  `ToolRun`/`Finding`/`Identity` (image scans also persist `Image`), aggregates
  honest coverage; `POST /api/scans/{id}/run` + `POST /api/scans/{id}/image` upload.
- `tools/` — adapters (`base.py` contract, `sitecheck.py` engine,
  `email/holehe.py`, `username/sherlock.py`, `web/{dns,whois,search,github}.py`,
  `registry.py`, `site_manifests/` real catalogs: username sherlock-derived,
  email curated live-verified).
- `tools/photo/` — local-first photo pipeline (`base.py` helpers, `hash.py`,
  `phash.py`, `exif.py`, `qr.py`, `registry.py`); `vision.py` routes vision/OCR
  to the approved Colab worker via `app/backend/services/vision_transport.py`
  (image as base64 in the job payload, optional dispatcher push, synchronous
  terminal-state wait) with graceful `blocked`/`interrupted`/`failed`
  degradation.
- `app/frontend` — React 19 + TypeScript SPA (Phase 12): hash-free state-based
  sidebar nav; typed `fetch('/api/*')` client (`src/api.ts`) via Vite dev proxy
  → `127.0.0.1:8000`; views in `src/views/*` (Dashboard, Scans, ScanDetail with
  polling + evidence/graph(SVG)/photo/risk tabs, Actions, Logs, Workers,
  Settings read-only); dark theme `App.css`. No router/UI/plot libraries.
  `tsc -b && vite build` clean, oxlint clean.
- `colab/` — worker package: `protocol.py` (versioned JobRequest/JobResult),
  `capabilities.py` (GPU/CPU/model probe), `handlers.py` (job-type registry +
  honest AI handlers), `dispatch.py` (fetch/ack transport), `worker.py`
  (execute_job lifecycle + run_worker_main loop), `privacy_guardian_worker.ipynb`.
- `app/backend/services/identity_graph.py` — deterministic relationship builder
  (Phase 9): rule-based `link_scan` (username→profile→website→domain, source
  labels, URL tokens from evidence), `rebuild_scan_graph`, and cross-scan
  `graph_for_scan` (collapses identities by `(kind, canonical)`). Exposed via
  `GET /api/scans/{id}/graph` + `POST /api/scans/{id}/graph/rebuild`.
- `app/backend/security/` — Phase 13 guardrails: `url_safety.py` (SSRF/unsafe-URL
  validation fed by OSINT targets + sitecheck manifest probe URLs),
  `middleware.py` (security response headers). Evidence caps + upload
  decompression-bomb guard live in `tools/base.py` and `app/backend/api/scans.py`.
- `app/backend/services/agent/` — agentic self-data investigator
  (`SPEC-agentic-investigator.md` + `SPEC-agent-*.md`): `registry.py` wraps the
  deterministic adapters behind strict-JSON `ToolSpec`s (email_lookup,
  username_lookup, web_search, dns, whois, github_user, site_check, photo_*,
  graph_expand, breach_check); `breach.py` k-anonymity (5-hex SHA-1 prefix,
  ephemeral, never plaintext); `model.py` AgentResult/AgentStep; `brain.py`
  AgentBrain (Colab 27B → local Ollama → graceful block); `loop.py` ReAct loop
  (allowlist, arg allowlisting, step budget, per-step timeout, deterministic
  removal proposals); `conversation_store.py` persisted redacted audit
  conversations; `removal_flow.py` confirm-gated removals. API in
  `app/backend/api/agent.py`: `GET /status`, `POST /chat` (SSE streaming),
  `POST /confirm` (approve/deny only), `GET /conversations[/{id}]`. V5 migration
  adds `agent_conversations` + `agent_messages`.
- `tests/security/` — 55 tests (SSRF, unsafe URL, path traversal, upload
  hardening, command injection, prompt injection, malicious webpage,
  authorization, CORS/exposure, security headers) + agent injection suite
  (`test_agent_injection.py`: no exec/URL tools, hybrid gate on
  reverse-image/breach, injected results stay inert).

## Module ownership map

| Concern | Module | Phase |
|---|---|---|
| API | `app/backend/api/*` | 5 ✅ |
| Scan orchestration | `app/backend/services/*` | 5–6 ✅ |
| Agent dispatch | `app/backend/agents/*` | 6 |
| Tool adapters | `app/backend/tools/*` + `tools/*` | 6–7 ✅(6) |
| OSINT adapters | `tools/{base,sitecheck,registry,email,username,web}` | 6 ✅ |
| Photo forensics | `tools/photo/*` | 7 ✅ |
| Models | `app/backend/models.py` | 4 ✅ |
| DB engine + migrations | `app/backend/database/*` | 4 ✅ |
| Security | `app/backend/security/*` | 13 ✅ |
| Colab worker | `colab/*` | 8 ✅ |
| Job dispatch | `app/backend/services/job_dispatcher.py` | 8 ✅ |
| Identity graph | `app/backend/services/identity_graph.py` | 9 ✅ |
| Risk engine | `app/backend/services/risk_engine.py` | 10 ✅ |
| Deletion research | `app/backend/services/deletion_research.py` | 11 ✅ |
| Deletion research (agent, confirm-gated) | `app/backend/services/agent/removal_flow.py` | 15 ✅ |
| Agent tool registry/loop | `app/backend/services/agent/{registry,breach,brain,loop}.py` | 15 ✅ |
| Agent API + conversations | `app/backend/api/agent.py`, `conversation_store.py`, V5 schema | 15 ✅ |
| Frontend UI | `app/frontend/src/*` | 12 ✅ |
| UI support API | `app/backend/api/{logs,settings}.py` | 12 ✅ |