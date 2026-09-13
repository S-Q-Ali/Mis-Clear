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

All master-plan phases delivered (15/15, **v0.3.0**). Full pipeline runs
locally: FastAPI control plane + React/TS SPA, OSINT discovery, photo
forensics, deterministic risk scoring, evidence-based privacy actions, and an
optional approved Colab worker for heavy vision/OCR (wired end-to-end).
252 pytest tests green; ruff clean; frontend build + lint clean.

## Features

- **OSINT discovery** — email / username account checks over real site catalogs
  (sherlock-derived username catalog, live-verified email services), DNS-over-HTTPS,
  RDAP whois, web + GitHub search, with no-lying coverage for every probe.
- **Photo forensics** — md5/sha256, perceptual d-hash, EXIF/GPS, QR decode;
  local AI vision when Ollama is present; hybrid scans route vision/OCR to the
  approved Colab worker via a real job protocol (image as base64, data_deleted
  after processing, never auto-"completed").
- **Evidence-based findings** — every result records source, URL, confidence,
  and coverage; nothing is reported that wasn't actually checked.
- **Deterministic risk scoring** — 0–100 from rules; AI explains, never invents.
- **Human-approved actions** — deletion research + DRAFT requests, approve/decline.
- **Identity graph** — cross-scan correlation with canonical merging.

## Requirements

- Python 3.11+ (managed via [uv](https://docs.astral.sh/uv/))
- Node.js 20+ / npm (frontend)
- Optional: [Ollama](https://ollama.com) for local AI
- Optional: an approved Colab/Databricks GPU runtime for heavy vision/OCR

## Quickstart

```
uv sync
cp .env.example .env                      # optional overrides
uv run pytest                 # backend tests
uv run uvicorn app.backend.main:app --host 127.0.0.1 --port 8000   # backend
cd app/frontend && npm install && npm run dev     # frontend (5173)
```

Or use the scripts: `scripts/setup.ps1`, `scripts/start.ps1`, `scripts/stop.ps1`.

### Heavy AI on the Colab GPU worker

AI models (reasoning `qwen3:8b`, vision `gemma3:4b`) default to **Colab-first
with a local-Ollama fallback** once a Colab endpoint is configured:

1. Run `colab/privacy_guardian_worker.ipynb` in Colab (7 sections: install Ollama,
   pull both models, clone repo, probe capabilities, run the dispatch loop).
2. Tunnel the **job dispatcher** on the laptop
   (`cloudflared tunnel --url http://127.0.0.1:8000`) and the **Ollama AI** port
   in Colab (notebook cell 7 already starts a `cloudflared` tunnel to 11434), then
   add both URLs to `.env`:
   ```
   PG_COLAB_OLLAMA_URL=https://<ollama-tunnel>
   PG_COLAB_JOB_DISPATCHER_URL=https://<dispatcher>/api
   ```
3. Restart the backend. New scans now default to `hybrid` and heavy vision/OCR
   routes to Colab; if Colab is unreachable the scan falls back to local Ollama
   instead of failing (details in `docs/COLAB_GPU_ARCHITECTURE.md`).

## Layout

```
app/backend/    FastAPI control plane (api, services, agents, workers, db, security)
app/frontend/   React + TypeScript UI
app/shared/     shared contracts (backend ↔ colab)
colab/          optional GPU worker (protocol, handlers, worker, notebook)
tools/          OSINT / photo / system adapters (site manifests, vision transport)
data/           local database, evidence, reports, uploads, cache, logs (gitignored)
tests/          unit / integration / security / e2e / fixtures
docs/           environment, architecture, security, threat model, tool matrix, …
scripts/        setup / start / stop / health-check
```

## Docs

- `MASTER_BUILD_INSTRUCTIONS.md` — controlling master plan
- `docs/PROJECT_DOCUMENTATION.md` — current product state (updated every phase)
- `docs/RELEASE_NOTES.md` — version history (v0.3.0)
- `docs/ENVIRONMENT_REPORT.md` — Phase 0 audit
- `docs/TOOL_MATRIX.md` — every external tool, wrapped behind `run(target) -> ToolResult`
- `docs/ARCHITECTURE.md`, `docs/SECURITY_MODEL.md`, `docs/THREAT_MODEL.md`
- `docs/COLAB_GPU_ARCHITECTURE.md` — optional GPU worker modes, protocol, privacy modes

## Privacy

Local by default. The only optional external components are the user-triggered
blocklist/OSINT lookups and the **explicitly approved** Colab worker. We never
store or request passwords and never auto-delete anything.