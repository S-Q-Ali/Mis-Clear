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
| 8 | Colab worker | ⬜ protocol skeleton only |
| 9–15 | Graph/Risk/Deletion/Frontend/Security/Testing/Audit | ⬜ |

## Current implementation

- **Backend** (`app/backend`): FastAPI app factory; REST control plane —
  `POST/GET /api/scans`, `/api/scans/{id}/findings`, `/api/scans/{id}/tool-runs`,
`/api/jobs`, `/api/workers`, `/api/reports/{scan_id}`; idempotent scan creation
   (`Idempotency-Key` header, dedupe + replay); consistent error envelope
   `{"error": {"code", "message", "details"}}` (422/404/409/500); contract-first
   camelCase Pydantic schemas (`app/backend/schemas.py`); SQLite engine
   (SQLAlchemy) with versioned migrations.
- **OSINT adapters** (`tools/`): stable `run(target) -> ToolResult` interface
  (`tools/base.py`); holehe/sherlock via site manifests (`tools/sitecheck.py`),
  web tools DNS-over-HTTPS (`tools/web/dns.py`), WHOIS/RDAP (`tools/web/whois.py`),
  DDG search (`tools/web/search.py`), GitHub (`tools/web/github.py`);
  `tools/registry.py` maps target types → adapters; `POST /api/scans/{id}/run`
  executes via `app/backend/services/scan_orchestrator.py` (persists ToolRun +
  Finding + Identity). All network in adapters is read-only public OSINT; a
  failure degrades to honest coverage, never a crash.
- **Photo forensics** (`tools/photo/`): local-first pipeline (Pillow + OpenCV
  headless + stdlib hashlib) — md5/sha256 (`hash.py`), perceptual d-hash
  (`phash.py`), EXIF/GPS (`exif.py`, untrusted metadata), QR decode (`qr.py`);
  `vision.py` routes vision/OCR to the approved Colab AI worker (Phase 8) with
  graceful `blocked` degradation (no fabricated findings). `POST
  /api/scans/{id}/image` uploads (validated magic bytes + size cap) to
  `data/uploads`, then the orchestrator persists an `Image` row (hashes/pHash)
  + findings for `targetType=image` scans.
- **Frontend** (`app/frontend`): Vite + React + TypeScript scaffold (builds clean).
- **Protocol** (`colab/protocol.py`): versioned `JobRequest`/`JobResult` dataclasses.
- **Colab worker** (`colab/`): `capabilities.py` advertises GPU/CPU/models
  deterministically (`nvidia-smi` optional), `handlers.py` registers job types
  (`reasoning` → Ollama; vision/OCR/barcode/embeddings degrade honestly when
  unconfigured — never fabricated output), `worker.py` runs the master-plan §13
  lifecycle (`execute_job`: protocol → expiry → handler → temp cleanup →
  `data_deleted:true`; `run_worker_main` poll-proc-ack loop with reconnect),
  `dispatch.py` covers fetch/ack transport; runnable `privacy_guardian_worker.ipynb`.
  Laptop side: `app/backend/services/job_dispatcher.py` submits `JobRequest` to
  `colab_job_dispatcher_url` (empty → job stays queued with an honest
  "dispatcher not configured" error), polls results, expires late jobs as
  `interrupted` (never auto-completed); API `POST /api/jobs/{id}/dispatch` +
  `/poll`. End-to-end Colab transport is optional and offline-safe.
- **Tests**: `tests/unit/*`, `tests/integration/*`; 105 pytest functions green
  + legacy suite intact. Adapter tests run on fake transports (httpx.MockTransport)
  / synthetic images generated at test time — no live network, no real personal data.

## Architecture (landscape)

```
LAPTOP ── React+TS UI → FastAPI control plane → scan orchestrator
   → local agents/tools (email/username/web/photo/risk)
   → SQLite + evidence store
   → optional Colab job dispatcher (explicit approval only)
Colab = disposable GPU worker (vision/OCR/embedding), never system of record.
```

## Dependencies

- Backend: fastapi, uvicorn, pydantic, pydantic-settings, sqlalchemy, httpx, pillow, opencv-python-headless, python-multipart (managed via `uv`, `pyproject.toml`).
- Frontend: react, typescript, vite (generated scaffold; Tailwind + UI primitives in Phase 12).
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