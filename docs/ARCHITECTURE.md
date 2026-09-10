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

## Current (Phase 1 realisation)

- `app/backend/main.py` — FastAPI `create_app()`; CORS restricted to local Vite origin; `/health` wired.
- `app/backend/config.py` — `Settings` (env prefix `PG_`, `.env` support).
- `app/backend/database/engine.py` — SQLite `engine`, `SessionLocal`, `init_db()`, `get_db()`.
- `app/frontend` — Vite React-TS scaffold, dev server on 5173.
- `colab/protocol.py` — job protocol types.

## Module ownership map

| Concern | Module | Phase |
|---|---|---|
| API | `app/backend/api/*` | 5 |
| Scan orchestration | `app/backend/services/*` | 5 |
| Agent dispatch | `app/backend/agents/*` | 5 |
| Tool adapters | `app/backend/tools/*` + `tools/*` | 6–7 |
| Models | `app/backend/models.py` | 4 ✅ |
| DB engine + migrations | `app/backend/database/*` | 4 ✅ |
| Security | `app/backend/security/*` | 13 |
| Colab worker | `colab/*` | 8 |