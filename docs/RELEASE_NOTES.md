# Release Notes — Privacy Guardian

## v0.6.0 (2026-09-25) — Uncensored agent brain on Colab

- **Agentic self-data investigator** (Phase 15-agent, chat-driven dig into the
  user's OWN public data): strict-JSON tool registry (`registry.py`) wrapping
  the deterministic adapters (email/username/web/dns/whois/github/site_check/
  photo/graph/breach), k-anonymity breach check (`breach.py`, 5-hex SHA-1
  prefix, ephemeral, `PG_BREACH_API_URL`), ReAct loop with allowlist + arg
  allowlisting + step budget + `<untrusted>` result wrapping, SSE chat
  (`/api/agent/chat`) with persisted redacted conversations (V5 schema), and
  confirm-gated removals (`POST /api/agent/confirm`, approve|deny only — no
  confirm, no action). Injection/hybrid-gate security suite.
- **Uncensored brain** (`PG_AGENT_MODEL`, default `qwen3.8-27b-unc`):
  `AgentBrain` forwards the chosen model verbatim to the approved Colab Ollama
  tunnel; the Colab notebook now pulls
  `hf.co/JonathanColetti/Qwen3.8-27B-Uncensored-GGUF` (quant `UNCENSORED_QUANT`,
  default `Q4_K_M`), creates the `qwen3.8-27b-unc` alias via the Ollama
  `/api/create` endpoint, and prints the `PG_AGENT_MODEL` value next to the
  tunnel URL. Model output stays **data, never instructions** (T17 added to
  THREAT_MODEL.md; brain routing contract locked by `test_agent_brain.py`).
- **Health-ping fix**: `api.ts` `getHealth()` pointed at `/api/health` (404);
  canonical route is `/health`. Guarded by `test_health.py` (`/health` 200,
  `/api/health` 404).
- **Tier-B readiness for the 27B brain**: per-step brain budget raised
  25s → **120s** (`agent_step_timeout_seconds`, env
  `PG_AGENT_STEP_TIMEOUT_SECONDS`; slow T4 cold starts may need 180-300s);
  `/api/agent/status` now reports the resolved `model` so the 27B is
  verifiable; the notebook alias cell is best-effort (idempotent, prints the
  real error body, falls back to the full `hf.co/...` tag as
  `AGENT_BRAIN_MODEL`).
- **Uncensored 27B syntax + tool listing fixes (live smoke-verified)**: (a)
  `AgentBrain.complete` now forwards `format:"json"` (allowed by
  `OllamaBackend`), so the thinking-mode 27B emits grammar-constrained valid
  JSON instead of prose — the loop's `parse_action` never sees a "parse
  failure" anymore; (b) the system prompt now embeds the **exact tool
  manifest** (`build_system_prompt`, names + arg keys + descriptions) so the
  model stops inventing tool names like `read_file`. Tier B live smoke
  (Colab tunnel → laptop backend → real
  `hf.co/JonathanColetti/Qwen3.8-27B-Uncensored-GGUF:Q4_K_M`): direct
  `/api/generate` probe 200 (warm, ~47 tok/s), `/api/agent/status`
  `backend=colab-ollama` + full model, and an end-to-end `graph_expand` chat
  that planned the tool call, executed it, surfaced evidence, and answered
  verbatim. Note: the current Colab has **no `qwen3.8-27b-unc` alias**
  (`/api/create` 400, `generate` 404) — `PG_AGENT_MODEL` must stay the full
  `hf.co/...` tag.
- **Verification**: 415 pytest functions green; ruff clean (`app tests`); frontend
  `tsc -b && vite build` + oxlint clean.

## v0.5.0 (2026-09-24) — Honest filing bundle (Phase 17)

- **Filing bundle download** (`app/backend/services/filing_bundle.py` +
  `GET /api/scans/{id}/filing-bundle`): stdlib-only, byte-deterministic ZIP of
  one scan built **only from REAL, already-committed rows** — findings, actions,
  execution attempts, scan-scoped audit trail, deterministic identity graph and
  risk breakdown, plus a manifest that never claims anything was removed unless
  an execution actually re-verified it. Honesty contract: `autoSent: false`,
  fabricated entries `0`, `removed`/`requiresManual` counted only from recorded
  executions; the only non-deterministic marker is the real UTC `generatedAt`.
  Filing stays a human action — the bundle is evidence for it, never a fake
  "filed" claim.
- **Verification**: unit (determinism except `generatedAt`, real-rows-only
  counts, no fabricated domains) + integration (real ZIP download over the
  control plane with honest attachment headers, 404). ruff clean.

## v0.4.0 (2026-09-14) — Personal-detail takedowns + NSFW/removal executor

- **Categorized takedown procedures** (Phase 16): curated
  `tools/site_manifests/removal.json` maps finding/photo channels to official
  removal records; every input-first finding that needs deletion research now
  also gets a `RemovalStrategy` (channel + procedure + official removals URL +
  verifier + channel-attempt cap). Image/NSFW findings route to the `adult`
  category takedown; unknown domains take an honest `known=False` path (no
  invented URLs/steps).
- **NSFW/sensitive classification**: NSFW image/brand checks now run as a real
  async Colab `nsfw_analysis` job (`tools/photo/nsfw.py` → `colab/handlers.py`),
  hybrid-first with honest strict-local blocking (never fabricating a verdict).
- **AI removal-draft refinement**: `tools/colab draft_refinement.py` tightens
  removal-request wording server-side with a deterministic URL-integrity
  post-check that discards any URL the source did not provide — an AI never
  invents a removal destination.
- **Automated removal executor** (`app/backend/services/removal_executor.py`):
  per-finding/per-action removal attempt ladder driven by the UI "Remove data"
  button. Every attempt runs through the finding's channel verifier, never
  fabricates a removal, escalates honestly to `requires_manual` (login-gated /
  official-url-only flows), requires human approval (buttons are research
  launchers, not auto-senders), and only reports `removed` after real
  re-verification. Every attempt is audited in the new `action_executions`
  table (migration V4). API `POST /api/findings/{id}/remove` + `/api/actions/{id}/remove`.
- **Frontend**: per-finding "Remove data" button + removal/execution status
  panels (site advisory, verification badges, official URLs) in the Findings
  tab; actions view shows execution summaries. Build + lint clean.
- **Verification**: 240 pytest functions green (198 unit + 42 integration; the 3
  env-gated dispatch/settings cases deselected in CI), ruff clean on touched
  files, frontend `tsc -b && vite build` + oxlint clean.

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
- **Ollama install fix**: Ollama retired the bare `ollama-linux-amd64` binary
  URL (now 404); the notebook cell downloads the `ollama-linux-amd64.tar.zst`
  archive and decompresses with `zstd` (pip `zstandard` fallback when the tool
  is missing). Dispatcher loop also warns when `COLAB_JOB_DISPATCHER_URL` uses a
  `.api` dot‑suffix instead of the `/api` path.
- **Notebook completed**: `colab/privacy_guardian_worker.ipynb` now implements
  the full 7-section sequence — clone repo/deps, capability probe, the dispatcher
  loop (refuses to run without a dispatcher URL), and an optional `cloudflared`
  tunnel cell that prints the Colab Ollama URL for `PG_COLAB_OLLAMA_URL`. Docs
  (`README`, `COLAB_GPU_ARCHITECTURE.md`, `colab/README.md`) updated to the new
  cell layout with both tunnel directions.

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
  notebook auto-installs Ollama (`ollama-linux-amd64.tar.zst` archive download)
  before the dispatch loop; findings pageSize capped at the backend max (100).

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