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
| 2 | Skills/Graphify | 🔶 skills installed; Graphify integration pending |
| 3 | Local AI (Ollama) | ⬜ blocked on Ollama installation |
| 4 | Database schema | ⬜ placeholder models only |
| 5 | Backend API | ⬜ only `/health` exists |
| 6 | OSINT adapters | ⬜ empty packages |
| 7 | Photo forensics | ⬜ empty packages |
| 8 | Colab worker | ⬜ protocol skeleton only |
| 9–15 | Graph/Risk/Deletion/Frontend/Security/Testing/Audit | ⬜ |

## Current implementation

- **Backend** (`app/backend`): FastAPI app factory, `/health` endpoint,
  pydantic-settings config, SQLite engine (SQLAlchemy, schema lands in Phase 4).
- **Frontend** (`app/frontend`): Vite + React + TypeScript scaffold (builds clean).
- **Protocol** (`colab/protocol.py`): versioned `JobRequest`/`JobResult` dataclasses.
- **Tests**: `tests/unit/test_health.py`; 18 pytest functions green.

## Architecture (landscape)

```
LAPTOP ── React+TS UI → FastAPI control plane → scan orchestrator
   → local agents/tools (email/username/web/photo/risk)
   → SQLite + evidence store
   → optional Colab job dispatcher (explicit approval only)
Colab = disposable GPU worker (vision/OCR/embedding), never system of record.
```

## Dependencies

- Backend: fastapi, uvicorn, pydantic, pydantic-settings, sqlalchemy, httpx (managed via `uv`, `pyproject.toml`).
- Frontend: react, typescript, vite (generated scaffold; Tailwind + UI primitives in Phase 12).
- AI: Ollama (Qwen-family local reasoning; Gemma/Qwen-VL vision), models configurable.
- OSINT (planned, Phase 6): holehe, sherlock, maigret, WHOIS/DNS, public search — behind stable adapters.
- Image (planned, Phase 7): EXIF, OCR, hashes, pHash, local vision.

## Security posture (summary)

Local-only by default; hybrid/Colab requires explicit approval; no passwords stored
or requested; never fabricate evidence; all web content treated as untrusted data.
See `docs/SECURITY_MODEL.md` and `docs/THREAT_MODEL.md`.

## Known limitations

- Ollama not installed → AI features degrade gracefully to "unavailable".
- Local GPU (MX250 2 GB) is weak → heavy batches target approved Colab worker.
- No destructive action is one-click; user approval is mandatory.
- Coverage is honest: sources checked vs. sources unavailable are both reported.