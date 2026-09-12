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
- `app/backend/api/{health,scans,findings,jobs,workers,reports}.py` — REST control plane
  (handlers: scans CRUD/findings/tool-runs, jobs CRUD, workers status/probe, reports aggregation).
- `app/backend/services/{model_router,idempotency}.py` — AI routing; idempotency keys
  (`idempotency_keys` table: atomic claim, replay/mismatch/in-flight resolution).
- `app/backend/models.py` + `database/migrations.py` — 9 tables + versioned migrations (v3).
- `app/backend/services/scan_orchestrator.py` — runs adapters for a scan, persists
  `ToolRun`/`Finding`/`Identity` (image scans also persist `Image`), aggregates
  honest coverage; `POST /api/scans/{id}/run` + `POST /api/scans/{id}/image` upload.
- `tools/` — adapters (`base.py` contract, `sitecheck.py` engine,
  `email/holehe.py`, `username/sherlock.py`, `web/{dns,whois,search,github}.py`,
  `registry.py`, `site_manifests/` samples).
- `tools/photo/` — local-first photo pipeline (`base.py` helpers, `hash.py`,
  `phash.py`, `exif.py`, `qr.py`, `registry.py`); `vision.py` routes vision/OCR
  to the approved Colab worker (Phase 8) with graceful `blocked` degradation.
- `app/frontend` — Vite React-TS scaffold, dev server on 5173.
- `colab/` — worker package: `protocol.py` (versioned JobRequest/JobResult),
  `capabilities.py` (GPU/CPU/model probe), `handlers.py` (job-type registry +
  honest AI handlers), `dispatch.py` (fetch/ack transport), `worker.py`
  (execute_job lifecycle + run_worker_main loop), `privacy_guardian_worker.ipynb`.

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
| Security | `app/backend/security/*` | 13 |
| Colab worker | `colab/*` | 8 ✅ |
| Job dispatch | `app/backend/services/job_dispatcher.py` | 8 ✅ |