# Release Notes — Privacy Guardian

## v0.3.1 (2026-09-13) — Colab-first AI with local fallback

- **Heavy AI models are now Colab-first**: configuring any Colab endpoint
  (`PG_COLAB_OLLAMA_URL` or `PG_COLAB_JOB_DISPATCHER_URL`) switches the
  effective default scan mode to `hybrid`, so vision/OCR/reasoning route to the
  approved Colab worker when available.
- **Graceful local fallback**: when a Colab job fails, interrupts, or times out,
  `VisionAdapter` now degrades to local Ollama (`_try_local`) instead of
  reporting `blocked` — only blocked when *no* local backend exists either.
  LOCAL ONLY scans never contact Colab (privacy gate preserved).
- Added two fallback tests (`test_hybrid_failed_job_falls_back_to_local`,
  `test_hybrid_interrupted_job_falls_back_to_local`).

### Verification (v0.3.1)
- **252 pytest functions green** (was 250); ruff clean; frontend build + lint clean.

## v0.3.0 (2026-09-13) — Colab vision transport + real OSINT catalogs

### What's new since 0.2.0
- **Photo vision/OCR → Colab wired end-to-end**: `tools/photo/vision.py` now runs
  hybrid scans through `app/backend/services/vision_transport.py` — the image
  travels as base64 in a real `Job` (optional dispatcher push, then a
  synchronous terminal-state wait with an honest expiry/timeout; never an
  auto-"completed" result). Worker handlers in `colab/handlers.py` forward the
  image to Ollama's native `images` parameter; a completed job becomes an
  `image_vision` finding.
- **Real site catalogs**: `tools/site_manifests/username.json` generated from
  sherlock's catalog (MIT, ~256 https-only sites, NSFW + placeholder + non-https
  excluded); `tools/site_manifests/email.json` curated from live-verified public
  services (Spotify, X.com, LastPass, Duolingo, WordPress.com) with strict
  exists/missing markers. GET-mode checks now report `None` (inconclusive) when
  markers are declared but unmatched — no false-positive guesses.
- **Server responsiveness fix**: the image-upload route runs the blocking scan on
  a threadpool (`run_in_threadpool`) — previously it stalled the whole event
  loop, making `/api/jobs/next` unresponsive during a scan.
- **SQLite concurrency**: `build_engine` enables WAL + 30s busy timeout so the
  worker protocol's writes queue gracefully instead of raising
  `database is locked`.
- **Final Phase-15 audit sweep**: no secrets, external-call whitelist verified,
  no broken links, manifests + engine proven by tests.

### Verification (v0.3.0)
- **250 pytest functions green** (vision transport unit + E2E over real HTTP
  with a simulated worker round-trip included).
- ruff clean on changed modules; frontend `npm run build` + `lint` clean.

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