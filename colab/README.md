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
- `privacy_guardian_worker.ipynb` — runnable notebook (7 sections: config → Ollama → models → clone → probe → loop → tunnel)

## Rules
- Never store the primary evidence database in Colab.
- Never put credentials in job payloads.
- If Colab disappears mid-job → `status: interrupted`, never `completed`.
- Temporary sensitive data is deleted before the final acknowledgement.
- Heavy/approved work only; local-only mode must work with Colab absent.

## Running
1. Open `privacy_guardian_worker.ipynb` in Colab and run the 7 sections:
   1. Configuration — set `COLAB_JOB_DISPATCHER_URL`
   2. Install Ollama (binary install, server on `0.0.0.0:11434`)
   3. Download AI models (`qwen3:8b` + `gemma3:4b` + uncensored 27B `qwen3.8-27b-unc` by
      default; quant via `UNCENSORED_QUANT` — T4 `Q4_K_M`, L4 `Q5_K_M`, A100 `Q6_K`/`Q8_0`)
   4. Clone repo + deps (`git clone` + `sys.path` + `httpx`)
   5. Capability probe (GPU/CPU/models advertisement)
   6. Dispatch loop — poll-proc-ack vs the laptop dispatcher
   7. Expose Colab Ollama (optional `cloudflared` tunnel for `PG_COLAB_OLLAMA_URL` +
      prints `PG_AGENT_MODEL=qwen3.8-27b-unc` for the agent brain)
2. Set `COLAB_JOB_DISPATCHER_URL` to a tunnel exposing the laptop's `127.0.0.1:8000`
   (e.g. `cloudflared tunnel --url http://127.0.0.1:8000`); the worker polls
   `GET {dispatcher}/jobs/next` and acks `POST {dispatcher}/jobs/{job_id}/result`
   with the matching `PG_COLAB_JOB_DISPATCHER_URL` in `.env`.