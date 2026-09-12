"""Shared HTTP transport between the Colab worker and the laptop dispatcher.

Endpoints (worker → laptop):
    GET  {dispatcher}/jobs/next   (advertises capabilities)  → JobRequest | None
    POST {dispatcher}/jobs/{job_id}/result                   → ack

No credentials are ever sent. All failures surface as exceptions the worker
loop turns into reconnects.
"""

from __future__ import annotations

from typing import Any

import httpx

from colab.capabilities import CapabilityReport
from colab.protocol import JobRequest, JobResult


def fetch_next_job(
    dispatcher_url: str,
    *,
    caps: CapabilityReport | None = None,
    client: httpx.Client | None = None,
) -> JobRequest | None:
    """Ask the laptop dispatcher for the next approved job (advertise caps)."""
    advertise: dict[str, Any] = caps.advertise() if caps is not None else {}
    with (client if client is not None else httpx.Client(timeout=10)) as http:
        resp = http.get(
            f"{dispatcher_url.rstrip('/')}/jobs/next",
            params={"worker": "privacy-guardian"},
            headers={"X-Worker-Capabilities": _compact_caps(advertise)},
        )
        resp.raise_for_status()
        if resp.status_code == 204 or not resp.content:
            return None
        data = resp.json()
        if not data:
            return None
        return JobRequest.from_dict(data)


def submit_result(
    dispatcher_url: str,
    result: JobResult,
    *,
    client: httpx.Client | None = None,
) -> bool:
    """Acknowledge a finished job to the laptop dispatcher."""
    with (client if client is not None else httpx.Client(timeout=10)) as http:
        resp = http.post(
            f"{dispatcher_url.rstrip('/')}/jobs/{result.job_id}/result",
            json=result.to_dict(),
        )
        return resp.status_code < 300


def _compact_caps(caps: dict[str, Any]) -> str:
    parts = []
    if caps.get("gpu"):
        parts.append("gpu:" + ",".join(str(g) for g in caps.get("gpus", [])))
    if caps.get("models"):
        parts.append("models:" + ",".join(str(m) for m in caps["models"]))
    return ";".join(parts)[:500]