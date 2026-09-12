# Colab GPU Worker (Phase 8)

Optional heavy-computation worker. The laptop stays the system of record.

## Layout
- `protocol.py` — versioned job protocol (`JobRequest`/`JobResult`)
- `capabilities.py` — deterministic GPU/CPU/model advertisement probe
- `handlers.py` — job-type handler registry + honest AI handlers (Ollama reasoning,
  vision/OCR/barcode/embeddings degrade with clear errors when unconfigured)
- `dispatch.py` — `fetch_next_job`/`submit_result` transport (versioned header)
- `worker.py` — stateless lifecycle: `execute_job` (protocol → expiry → handler →
  temp cleanup → `JobResult`) and `run_worker_main` poll-proc-ack loop
- `privacy_guardian_worker.ipynb` — runnable notebook (setup → probe → loop)

## Rules
- Never store the primary evidence database in Colab.
- Never put credentials in job payloads.
- If Colab disappears mid-job → `status: interrupted`, never `completed`.
- Temporary sensitive data is deleted before the final acknowledgement.
- Heavy/approved work only; local-only mode must work with Colab absent.

## Running
1. Open `privacy_guardian_worker.ipynb` in Colab and run all cells.
2. Set `COLAB_JOB_DISPATCHER_URL` to a tunnel exposing the laptop dispatcher
   (`POST /api/jobs`, then `/jobs/{id}/dispatch` + `/jobs/{id}/poll` on the laptop
   with the matching `PG_COLAB_JOB_DISPATCHER_URL` in `.env`).