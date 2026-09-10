"""Colab GPU worker (usable inside the notebook or standalone).

Lifecycle: start → advertise capabilities → receive approved job → process →
return structured result → delete temporary sensitive data → acknowledge.

The worker is stateless/disposable and NEVER stores the primary evidence DB.
Populated fully in Phase 8; skeleton now.
"""

from __future__ import annotations

from typing import Callable

from colab.protocol import JobResult


def run(job: dict, processor: Callable[[dict], dict]) -> JobResult:
    """Process one job dict through a processor and wrap it in a JobResult."""
    result = JobResult(job_id=str(job.get("job_id", "")))
    result.started_at = result.completed_at
    try:
        out = processor(job.get("payload", {}))
        result.status = "completed"
        result.result = out
    except Exception as exc:  # noqa: BLE001 - report, do not crash
        result.status = "failed"
        result.errors = [f"{type(exc).__name__}: {exc}"]
    return result