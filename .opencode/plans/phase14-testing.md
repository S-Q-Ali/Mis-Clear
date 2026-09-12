# Phase 14 — Testing (master plan §14)

**Goal:** Prove the whole stack under real conditions and under failure.
Existing state: unit (123), integration (38), security (55). Missing per §14:
**E2E** (0 tests) and a dedicated **failure/recovery** suite.

Synthetic fixtures only — never real personal data.

## Slice A — E2E over real HTTP (`tests/e2e/`)

Real uvicorn server on `127.0.0.1:<ephemeral-port>` (thread), real SQLite DB in
tmp, driven by `httpx` over genuine sockets. OSINT registry replaced with fake
adapters (same-process monkeypatch) so no external network; the real photo
pipeline runs for image scans (vision blocked with no AI backend).

- `conftest.py`: settings patch + engine init + `ServerManager`
  (start/stop uvicorn, free-port, readiness wait) + `http` fixture.
- `test_full_flow_http.py`: create → run → findings → tool-runs → graph →
  risk → deletion-research → actions approve → logs.
- `test_photo_flow_http.py`: create image scan → multipart upload (PNG) →
  completed → image detail → graph → tool-runs (vision blocked).
- `test_restart_and_headers_http.py`: security headers over real HTTP; health;
  **server restart with same DB** preserves scans/findings; re-run after
  restart stays consistent.

## Slice B — Failure & recovery (`tests/failure_recovery/`)

Deterministic failure injection, then assert recovery:

- `test_ollama_retry.py` — transient `ConnectError` then success (2 attempts,
  result returned); persistent 500 exhausts retries+1 attempts then raises
  `ModelUnavailableError` (clean, no crash). Sleep monkeypatched.
- `test_dispatcher_recovery.py` — submit fails (dispatcher down) → errors
  recorded; later submit succeeds → disposition `submitted`. And failed-submit
  job later recovered via `poll_job` → completed.

Already covered elsewhere (not duplicated): worker crash isolation + temp
cleanup (`test_worker`), orchestrator crash isolation (`test_scan_run`),
expiry `interrupted` never auto-completed (`test_job_dispatcher`),
concurrent-run 409 guard (`test_orchestrator_rejects_running_scan`).

## Slice C — Verification + docs

- `uv run pytest` (expect ≈ +12 → ~229), ruff on new files, `npm run build`
  + `npm run lint` untouched but confirmed.
- Docs: `docs/PROJECT_DOCUMENTATION.md` Phase 14 row + test counts;
  `SESSION_STATE.md` Phase 14 entry (gitignored).
- Commits: `test: phase 14 - e2e over real HTTP (uvicorn + httpx + temp DB)`,
  `test: phase 14 - failure/recovery battery (ollama retry, dispatcher recovery)`,
  `docs: phase 14 - testing phase status + counts`. Push.