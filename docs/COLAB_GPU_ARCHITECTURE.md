# COLAB_GPU_ARCHITECTURE

## Role
Optional **temporary compute runtime** for heavy work. Two worker modes:

1. **Colab GPU Worker** — batch vision/OCR/embeddings (image pipelines, Phase 7/8).
2. **Colab Ollama AI Worker** — Ollama served from a Colab/site tunnel
   (e.g. `collab-ollama`), used by `ModelRouter` for inference when approved.

Colab is never the system of record, and the app never depends on it:
Colab down → local Ollama (if any) → graceful degradation. Switching the remote
compute to a T4/L4/A100 server is a **configuration change** only.

## Routing (ModelRouter)
`app/backend/services/model_router.py`:
- Colab Ollama used only when **explicitly approved** AND available.
- `strict_local` (LOCAL ONLY mode) forbids Colab entirely.
- No backend available → `ModelUnavailableError` → UI shows AI as inactive; work continues.

## Privacy modes
- **LOCAL ONLY** — sensitive data never leaves the laptop.
- **HYBRID** — user explicitly approves selected data → Colab → inference →
  result back → temporary data cleanup (`data_deleted: true`).
- **OFFLINE** — no network AI processing at all.

## Data flow
```
Laptop: job created (approved, versioned protocol, payload references local IDs)
   → dispatcher → Colab worker
Worker: start → advertise capabilities → receive job → process
   → delete temporary sensitive data → return structured result → ack
Laptop: persist result + evidence; job status: completed/interrupted/failed
```

## Status semantics
- `completed` — only when finished cleanly.
- `interrupted` — Colab VM lost before finish (never auto-"completed").
- `failed` — error results returned.

## Protocol
`colab/protocol.py` — `JobRequest` (protocol_version=1, job_id, job_type,
created_at, expires_at, privacy_mode, payload, requested_capabilities, return_format)
and `JobResult` (status, started/completed_at, result, errors, data_deleted).

## Rules
- No credentials in payloads.
- Temporary data deleted before final ack (`data_deleted: true`).
- Hybrid always requires explicit user approval (default true).
- `expires_at` bounds job lifetime.

## Implementation
Phase 8 complete: notebook `privacy_guardian_worker.ipynb` (Colab Ollama install
via direct binary download, then the dispatch loop), `worker.py` lifecycle
(execute_job + run_worker_main loop), `capabilities.py` GPU probe,
`handlers.py` registry, `dispatch.py` transport, and laptop-side
`app/backend/services/job_dispatcher.py` (+ `POST /api/jobs/{id}/dispatch|poll`)
plus the direct worker protocol `GET /api/jobs/next` and
`POST /api/jobs/{job_id}/result`, simulating the full Colab lifecycle over real
HTTP in `tests/e2e/test_colab_worker_flow_http.py`.
End-to-end Colab transport pending Phase 9 wiring (photo vision/OCR/barcode) —
everything degrades honestly (`blocked`/`interrupted`/`failed`) with Colab absent.
Tested with synthetic data only (never real personal data).