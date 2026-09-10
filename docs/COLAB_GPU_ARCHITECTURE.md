# COLAB_GPU_ARCHITECTURE

## Role
Optional GPU worker for heavy computation (vision batch, OCR batch, embeddings).
Never the system of record. Local-only mode works without it.

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
Phase 8: notebook `privacy_guardian_worker.ipynb`, `worker.py` lifecycle, GPU
detection, model loading, timeout, retry/reconnect, cleanup. Test with synthetic
data first (never real personal data).