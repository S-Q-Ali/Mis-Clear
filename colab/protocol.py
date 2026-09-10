"""Versioned job protocol between the laptop control plane and the Colab worker.

Never put credentials or personal data in job payloads. Payloads may reference
evidence IDs stored locally; the worker never owns the evidence store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from datetime import datetime, timezone

PROTOCOL_VERSION = "1"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class JobRequest:
    protocol_version: str = PROTOCOL_VERSION
    job_id: str = ""
    job_type: str = ""
    created_at: str = field(default_factory=utcnow_iso)
    expires_at: str = ""
    privacy_mode: str = "hybrid_approved"
    payload: dict[str, Any] = field(default_factory=dict)
    requested_capabilities: list[str] = field(default_factory=list)
    return_format: str = "json"

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "job_id": self.job_id,
            "job_type": self.job_type,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "privacy_mode": self.privacy_mode,
            "payload": self.payload,
            "requested_capabilities": self.requested_capabilities,
            "return_format": self.return_format,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobRequest":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class JobResult:
    protocol_version: str = PROTOCOL_VERSION
    job_id: str = ""
    status: str = "interrupted"  # completed | interrupted | failed
    started_at: str = ""
    completed_at: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    data_deleted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "job_id": self.job_id,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "errors": self.errors,
            "data_deleted": self.data_deleted,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobResult":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})