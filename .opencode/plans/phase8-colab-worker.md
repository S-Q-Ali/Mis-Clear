# Plan — Phase 8: Colab Worker (job transport + lifecycle)

Controlling spec: master plan §13 (worker lifecycle), §14 (versioned job
protocol), COLAB_GPU_ARCHITECTURE. Colab = disposable temporary compute; never
system of record; laptop stays authoritative; Colab down → honest `interrupted`
(never auto-`completed`); local-only mode must work with Colab absent.

## Slices (thin vertical, TDD, each verified + committed)
- A. `colab/capabilities.py` — deterministic GPU/CPU/model probe acceptable to
  the worker (`nvidia-smi` optional, synthetic parse, safe default = cpu + no models).
- B. `colab/handlers.py` — job handler registry (`register_handler(job_type, fn)`)
  + built-ins: `reasoning` (local Ollama @127.0.0.1, MockTransport-testable),
  `vision_analysis`/`ocr`/`barcode`/`embeddings` degrade honestly when no model.
  Removed: never fabricate results.
- C. `colab/worker.py` — real `execute_job(job, handlers, capabilities, tmp_root)`
  lifecycle: protocol_version check → expiry → capability gate → handler → temp
  cleanup → JobResult (completed/failed/interrupted/data_deleted); plus
  `run_worker_main()` notebook/CLI drive loop + `fetch_next_job`/`submit_result`.
- D. Laptop service `app/backend/services/job_dispatcher.py` — submit Job row →
  `JobRequest` POST to `colab_job_dispatcher_url` (httpx); poll → completed/
  interrupted/failed; empty URL → stays queued with honest error; `expires_at`
  bound; API `POST /api/jobs/{id}/dispatch` + `/poll` (vertical path).
- E. `privacy_guardian_worker.ipynb` — runnable notebook (setup → worker → monitor).
- F. Docs + SESSION_STATE + commit.

## Guardrails
- Synthetic tests only; no real GPU inference, no real Colab network.
- httpx.MockTransport everywhere in tests (zero real network).
- No credentials in payloads; temp data deleted before ack (`data_deleted:true`).
- Gap: `colab_job_dispatcher_url` empty in this env → dispatch reports
  `DISpatcher not configured`; VisionAdapter photo wiring stays Phase 9/12.