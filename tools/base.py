"""Shared OSINT tool adapter contract (Phase 6).

Every adapter exposes:

    run(target) -> ToolResult

and reports findings using the evidence model from master plan §11
(confidence: confirmed/probable/possible/weak/false_positive,
severity: critical/high/medium/low/informational).

All web content adapters consume is treated as untrusted input; adapters
never execute instructions embedded in remote content.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

VALID_CONFIDENCE = {"confirmed", "probable", "possible", "weak", "false_positive"}
VALID_SEVERITY = {"critical", "high", "medium", "low", "informational"}


@dataclass
class ToolFinding:
    """A single evidence-row before persistence (mirrors the ORM Finding)."""

    type: str
    title: str
    source: str
    url: str | None = None
    evidence: str | None = None
    confidence: str = "possible"
    severity: str = "low"
    scope: str | None = None

    def __post_init__(self) -> None:
        if self.confidence not in VALID_CONFIDENCE:
            raise ValueError(f"invalid confidence: {self.confidence}")
        if self.severity not in VALID_SEVERITY:
            raise ValueError(f"invalid severity: {self.severity}")


@dataclass
class ToolResult:
    """Outcome of one adapter run.

    status: completed | failed | blocked
    coverage: {"sources_total", "sources_checked", "sources_failed", "note"} (counts)
    """

    tool: str
    status: str = "completed"
    duration_ms: int = 0
    findings: list[ToolFinding] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    raw_reference: str | None = None
    coverage: dict[str, Any] = field(default_factory=dict)


class ToolAdapter(ABC):
    """Stable interface for any OSINT tool (master plan Phase 6)."""

    name: str = ""
    target_types: tuple[str, ...] = ()

    @abstractmethod
    def run(self, target: str) -> ToolResult:
        """Probe `target` and return a ToolResult. Must never raise for I/O errors."""