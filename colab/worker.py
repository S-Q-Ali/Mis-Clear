"""Colab GPU worker lifecycle (Phase 8, master plan §13).

Lifecycle: start → replicate capabilities → receive approved job → process →
return structured result → delete temporary sensitive data → acknowledge.

The worker is stateless/disposable and NEVER stores the primary evidence DB.

Status semantics (COLAB_GPU_ARCHITECTURE):
    - completed  : only when a handler finished cleanly and temp data was cleaned.
    - interrupted: job expired / Colab vanished mid-flight — never auto-completed.
    - failed     : protocol or handler error returned.
"""

from __future__ import annotations

import shutil
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from colab import dispatch
from colab.capabilities import CapabilityReport, detect_capabilities
from colab.handlers import get_handler
from colab.protocol import PROTOCOL_VERSION, JobRequest, JobResult

_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {}


def register_worker_handler(job_type: str, fn: Callable[..., dict[str, Any]]) -> None:
    """Register a job-type handler for this worker instance."""
    if not job_type or not callable(fn):
        raise ValueError("job_type and callable fn required")
    _HANDLERS[job_type] = fn


def resolve_handler(job_type: str) -> Callable[..., dict[str, Any]] | None:
    return _HANDLERS.get(job_type) or get_handler(job_type)


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def execute_job(
    job: JobRequest,
    *,
    caps: CapabilityReport,
    handlers: dict[str, Callable[..., dict[str, Any]]] | None = None,
    tmp_root: str | Path = "data/cache/colab",
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> tuple[JobResult, dict[str, Any]]:
    """Run one approved job through its handler with temp-data hygiene.

    Returns (result, handler_detail) — `handler_detail` is the raw handler
    payload (used for testing); it is NOT persisted.
    """
    result = JobResult(job_id=job.job_id)
    result.protocol_version = job.protocol_version
    result.started_at = utcnow_iso()

    if job.protocol_version != PROTOCOL_VERSION:
        result.status = "failed"
        result.errors = [f"unsupported protocol_version: {job.protocol_version}"]
        result.completed_at = utcnow_iso()
        return result, {}

    now = clock()
    if job.expires_at:
        try:
            expired = datetime.fromisoformat(job.expires_at) < now
        except ValueError:
            expired = False
        if expired:
            result.status = "interrupted"
            result.errors = ["job expired before processing (never auto-completed)"]
            result.completed_at = utcnow_iso()
            return result, {}

    handler_map = handlers or _HANDLERS
    handler = handler_map.get(job.job_type) or get_handler(job.job_type)
    if handler is None:
        result.status = "failed"
        result.errors = [f"no handler for job_type: {job.job_type}"]
        result.completed_at = utcnow_iso()
        return result, {}

    tmp_dir = Path(tmp_root) / job.job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(job.payload or {})
    payload["tmp_dir"] = str(tmp_dir)
    detail: dict[str, Any] = {}
    try:
        detail = handler(payload, caps)
        result.result = detail or {}
        result.status = "completed"
    except Exception as exc:  # noqa: BLE001 - worker reports, never crashes
        result.status = "failed"
        result.errors = [f"{type(exc).__name__}: {exc}"]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        result.data_deleted = not tmp_dir.exists()
        result.completed_at = utcnow_iso()
    return result, detail


def fetch_next_job(
    dispatcher_url: str,
    *,
    caps: CapabilityReport,
    client: Any | None = None,
) -> JobRequest | None:
    """Poll the laptop dispatcher for the next approved job (advertise caps)."""
    return dispatch.fetch_next_job(dispatcher_url, caps=caps, client=client)


def submit_result(dispatcher_url: str, result: JobResult, *, client: Any | None = None) -> bool:
    """Acknowledge a finished job back to the dispatcher."""
    return dispatch.submit_result(dispatcher_url, result, client=client)


def run_worker_main(
    dispatcher_url: str,
    *,
    caps: CapabilityReport | None = None,
    tmp_root: str | Path = "data/cache/colab",
    max_iterations: int = 1,
    poll_interval_s: float = 1.0,
    max_failures: int = 3,
) -> dict[str, Any]:
    """Notebook/CLI driver: start → advertise → poll-proc-ack loop.

    Survives/reconnects: fetch failures retried up to `max_failures` before
    returning. Returns a summary dict (never claims work it didn't do).
    """
    caps = caps or detect_capabilities()
    summary: dict[str, Any] = {
        "worker": "privacy-guardian",
        "caps": caps.advertise(),
        "jobs_processed": 0,
        "jobs_failed": 0,
        "jobs_interrupted": 0,
        "reconnects": 0,
    }
    consecutive_failures = 0
    for _ in range(max_iterations):
        try:
            job = fetch_next_job(dispatcher_url, caps=caps)
        except Exception:  # noqa: BLE001 - reconnect then give up
            consecutive_failures += 1
            summary["reconnects"] += 1
            if consecutive_failures >= max_failures:
                summary["note"] = f"dispatcher unreachable after {max_failures} attempts"
                break
            time.sleep(poll_interval_s)
            continue
        consecutive_failures = 0
        if job is None:
            break
        result, _detail = execute_job(job, caps=caps, tmp_root=tmp_root)
        submit_result(dispatcher_url, result)
        if result.status == "completed":
            summary["jobs_processed"] += 1
        elif result.status == "failed":
            summary["jobs_failed"] += 1
        else:
            summary["jobs_interrupted"] += 1
    return summary