# COLAB_GPU_ARCHITECTURE

## Role
Optional **temporary compute runtime** for heavy work. Two worker modes:

1. **Colab GPU Worker** — batch vision/OCR/embeddings (image pipelines, Phase 7/8).
2. **Colab Ollama AI Worker** — Ollama served from a Colab/site tunnel
   (e.g. `collab-ollama`), used by `ModelRouter` for inference when approved.

Colab is never the system of record, and the app never depends on it:
Colab down → local Ollama (if any) → graceful degradation. Switching the remote
compute to a T4/L4/A100 server is a **configuration change** only.

## Routing (ModelRouter + VisionAdapter)
`app/backend/services/model_router.py`:
- Colab Ollama used only when **explicitly approved** AND available.
- `strict_local` (LOCAL ONLY mode) forbids Colab entirely.
- No backend available → `ModelUnavailableError` → UI shows AI as inactive; work continues.

**Colab-first with local fallback** — once any Colab endpoint is configured
(`PG_COLAB_OLLAMA_URL` or `PG_COLAB_JOB_DISPATCHER_URL`), the effective default
scan mode becomes `hybrid`, so heavy AI work (vision/OCR/reasoning) routes to
the approved Colab worker when available. If Colab is down, mid-scan or absent,
the pipeline degrades gracefully to local Ollama instead of blocking:
`Colab job failed/interrupted → VisionAdapter._try_local → completed locally`.
Sensitive data still requires explicit approval (scan_mode=hybrid); LOCAL ONLY
scans never contact Colab.

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
via direct `ollama-linux-amd64.tar.zst` archive download + `zstd` decompress,
then the dispatch loop), `worker.py` lifecycle
(execute_job + run_worker_main loop), `capabilities.py` GPU probe,
`handlers.py` registry, `dispatch.py` transport, and laptop-side
`app/backend/services/job_dispatcher.py` (+ `POST /api/jobs/{id}/dispatch|poll`)
plus the direct worker protocol `GET /api/jobs/next` and
`POST /api/jobs/{job_id}/result`, simulating the full Colab lifecycle over real
HTTP in `tests/e2e/test_colab_worker_flow_http.py`.
Phase 15 end-to-end: hybrid photo scans route vision/OCR through
`app/backend/services/vision_transport.py` (job created with the image as
base64 in the payload, optionally pushed to a configured dispatcher inbox,
then a synchronous terminal-state wait with an honest expiry/timeout no
auto-completed result). The laptop's `tools/photo/vision.py` turns a
worker's completed text into an `image_vision` finding; worker handlers in
`colab/handlers.py` forward `image_base64` to Ollama's native `images`
parameter. Covered by `tests/e2e/test_vision_transport_http.py` (simulated
worker thread) and `tests/unit/test_photo_vision.py`.
Everything degrades honestly (`blocked`/`interrupted`/`failed`) with Colab absent
— when a local Ollama is available it is used as the graceful fallback; when
neither is available the scan reports `blocked`, never a fabricated result.
Tested with synthetic data only (never real personal data).

## Setup — Colab GPU Worker + Ollama AI

1. Open `colab/privacy_guardian_worker.ipynb` in Google Colab and run the cells
   (7 sections):
   1. **Configuration** — set `COLAB_JOB_DISPATCHER_URL` to the laptop tunnel.
   2. **Install Ollama** — binary install + server on `0.0.0.0:11434`.
   3. **Download AI models** — default `qwen3:8b` + `gemma3:4b` (GPU).
   4. **Clone repo + deps** — `git clone` + `sys.path` + `httpx`.
   5. **Capability probe** — advertises GPU/CPU/models.
   6. **Dispatch loop** — poll-proc-ack (`GET /jobs/next` → process →
      `POST /jobs/{job_id}/result`). Refuses to run without a dispatcher URL.
   7. **Expose Colab Ollama (optional)** — `cloudflared` tunnel to port 11434;
      prints the `https://<...>.trycloudflare.com` URL for `PG_COLAB_OLLAMA_URL`.
2. Two tunnels, one per direction:
   - **Job dispatcher** — created on the **laptop**, points at `127.0.0.1:8000`
     (e.g. `cloudflared tunnel --url http://127.0.0.1:8000`). Colab polls it via
     `GET {dispatcher}/jobs/next` and acks `POST {dispatcher}/jobs/{job_id}/result`.
   - **Ollama AI** — created in **Colab** (notebook cell 7), points at the local
     Ollama port 11434 so the laptop's `ModelRouter` can call `/api/generate`
     directly (reasoning) and send `images=[base64]` (vision).
3. Configure the laptop `.env`:
   ```
   PG_COLAB_OLLAMA_URL=https://<ollama-tunnel>          # direct AI inference
   PG_COLAB_JOB_DISPATCHER_URL=https://<dispatcher>/api # job transport
   ```
   With either set, new scans default to `hybrid` and AI work is Colab-first.
4. Restart the backend. The Workers page shows Colab availability; the Dashboard
   AI mode becomes `hybrid` once a Colab endpoint is configured.