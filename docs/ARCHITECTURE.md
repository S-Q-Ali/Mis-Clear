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
evidence, config, reports, approvals.

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
| Models | `app/backend/models.py` | 4 |
| DB engine | `app/backend/database/*` | 4 |
| Security | `app/backend/security/*` | 13 |
| Colab worker | `colab/*` | 8 |