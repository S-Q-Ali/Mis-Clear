# Release Notes — Privacy Guardian

## v0.2.0 (2026-09-13) — Full pipeline: 15/15 phases

Local-first privacy/OSINT assistant with evidence-based findings and
human-approved actions. All master-plan phases delivered.

### What's new since 0.1.0 (incremental)
- **Phase 13 — Security**: SSRF/unsafe-URL guardrail, security response
  headers, central evidence cap, upload decompression-bomb guard, 55-test
  security battery; dep audits clean (pip-audit 0, npm audit 0).
- **Phase 14 — Testing**: E2E suite over real HTTP (uvicorn + httpx + SQLite
  temp DB), failure/recovery battery (Ollama retry, dispatcher recovery);
  fixed `poll_job` UTC/naive compare bug.
- **Phase 15 — Audit**: scan `run` events now written to the audit log;
  release notes; docs sync.
- Colab follow-ups: direct worker protocol on the control plane
  (`GET /api/jobs/next`, `POST /api/jobs/{job_id}/result`) with E2E coverage;
  notebook auto-installs Ollama (direct binary download) before the dispatch
  loop; findings pageSize capped at the backend max (100).

### Full scope (Phase 0–15)
| Area | Delivered |
|---|---|
| Backend | FastAPI control plane — scans, findings, tool-runs, identity graph (+rebuild), risk, deletion research, actions, jobs, workers, reports, audit log, read-only settings |
| OSINT | sitecheck (holehe/sherlock manifests), DNS-over-HTTPS, RDAP whois, web search, GitHub enumeration |
| Photo forensics | md5/sha256/d-hash, EXIF + GPS, QR decode, vision→Colab (blocked offline), 20MB + 50MP upload guards |
| AI | deterministic ModelRouter (approved Colab → local Ollama → graceful fail), Ollama backend with retry |
| Colab worker | capabilities probe, handler registry, worker lifecycle, runnable notebook, laptop dispatcher + direct protocol |
| Identity graph | deterministic rule-based relationships, cross-scan canonical merge |
| Risk | deterministic 0–100 scoring (AI explains, never computes); false-positive hard gate |
| Deletion research | curated official procedures + DRAFT requests + human approve/decline |
| Frontend | React 19 + TS SPA — dashboard, scans, live investigation (evidence/graph/photo/risk/research), actions, logs, workers, settings |
| Privacy gates | local-by-default, Colab only with explicit approval, no passwords stored, evidence never fabricated, loopback-bound |

### Verification
- **235 pytest functions green** (unit 123, integration 39, security 55,
  e2e 12, failure/recovery 5) — synthetic fixtures only.
- `uvx pip-audit` 0 known vulnerabilities; `npm audit` (prod + dev) 0.
- ruff clean; `tsc -b && vite build` clean; oxlint 0 warnings / 0 errors.

### Run
```
# backend
uv sync
copy .env.example .env                    # optional PG_* overrides
uv run uvicorn app.backend.main:app --host 127.0.0.1 --port 8000

# frontend (dev)
cd app/frontend && npm install && npm run dev    # proxied to :8000

# tests
uv run pytest
```
See `scripts/setup.ps1`, `scripts/start.ps1`, `scripts/stop.ps1`.

### Known limitations
- No authentication — single-user, loopback-bound design decision (see
  `docs/THREAT_MODEL.md` residual risks).
- Ollama is optional; without it all AI-dependent tools report honest
  `blocked`/`unavailable` (app fully functional).
- Default site-check manifests are synthetic samples — replace with real
  catalogs (`PG_OSINT_MANIFEST_EMAIL/USERNAME`).
- OCR/barcode transport to Colab not wired end-to-end yet; vision degrades to
  `blocked` offline.
- Cache note (pre-pivot Mis-Clear): broad cache wipe is documented behavior.