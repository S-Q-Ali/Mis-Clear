# Privacy Guardian

**Local-first personal privacy / OSINT assistant.**

Investigates where your email, usernames, and photos surface publicly, confirms
evidence, correlates identities, scores your exposure risk, and prepares
**human-approved** privacy actions — all private by default, on your laptop.

> Formerly **Mis-Clear** (browser trace cleaner). This repo pivoted to the
> Privacy Guardian master plan (`MASTER_BUILD_INSTRUCTIONS.md`).

## Principles

- **Private > convenient** — everything stays local by default.
- **Evidence > assumptions** — every finding records source, URL, timestamp, confidence.
- **Local > cloud** — an optional, user-approved Colab worker handles heavy GPU work only.
- **Deterministic > opaque** — risk scoring uses deterministic rules.
- **Verified > claimed** — nothing is reported that wasn't actually checked.

## Status

Phase 0–1 complete (environment audit + bootstrap). See `docs/PROJECT_DOCUMENTATION.md`
for the phase table. Backend `/health` works; tests green.

## Requirements

- Python 3.11+ (managed via [uv](https://docs.astral.sh/uv/))
- Node.js 20+ / npm (frontend)
- Optional: [Ollama](https://ollama.com) for local AI (Phase 3)

## Quickstart

```
uv sync
uv run pytest                 # backend tests
uv run uvicorn app.backend.main:app --port 8000   # backend
cd app/frontend && npm install && npm run dev     # frontend (5173)
```

Or use the scripts: `scripts/setup.ps1`, `scripts/start.ps1`, `scripts/stop.ps1`.

## Layout

```
app/backend/    FastAPI control plane (api, services, agents, workers, db, security)
app/frontend/   React + TypeScript UI
app/shared/     shared contracts (backend ↔ colab)
colab/          optional GPU worker (protocol, worker, notebook)
tools/          OSINT / photo / system adapters (Phase 6–7)
data/           local database, evidence, reports, uploads, cache, logs (gitignored)
tests/          unit / integration / security / e2e / fixtures
docs/           environment, architecture, security, threat model, tool matrix, …
scripts/        setup / start / stop / health-check
```

## Docs

- `MASTER_BUILD_INSTRUCTIONS.md` — controlling master plan
- `docs/PROJECT_DOCUMENTATION.md` — current product state (updated every phase)
- `docs/ENVIRONMENT_REPORT.md` — Phase 0 audit
- `docs/SECURITY_MODEL.md`, `docs/THREAT_MODEL.md` — security posture

## Privacy

Local by default. The only optional external components are the user-triggered
blocklist/OSINT lookups and the **explicitly approved** Colab worker. We never
store or request passwords and never auto-delete anything.