# Colab GPU Worker (Phase 8)

Optional heavy-computation worker. The laptop stays the system of record.

## Layout
- `protocol.py` — versioned job protocol (`JobRequest`/`JobResult`)
- `worker.py` — stateless worker lifecycle
- `privacy_guardian_worker.ipynb` — runnable notebook (Phase 8)

## Rules
- Never store the primary evidence database in Colab.
- Never put credentials in job payloads.
- If Colab disappears mid-job → `status: interrupted`, never `completed`.
- Temporary sensitive data is deleted before the final acknowledgement.
- Heavy/approved work only; local-only mode must work with Colab absent.

_Generate `privacy_guardian_worker.ipynb` in Phase 8._