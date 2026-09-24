"""Agent output/step models (SPEC-agent-core)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)


class AgentAction(BaseModel):
    """The model's next move: either a tool call or a stop with an answer."""

    thought: str = ""
    action: ToolCall | None = None
    stop: bool = False
    answer: str = ""


class AgentStep(BaseModel):
    """One auditable lifecycle event the UI streams (SSE) and we persist."""

    kind: Literal["thought", "tool", "result", "evidence", "error", "confirm"]
    label: str = ""
    detail: str = ""
    evidence: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class AgentResult(BaseModel):
    steps: list[AgentStep] = Field(default_factory=list)
    blocked: bool = False
    answer: str = ""
    confirm_required: list[str] = Field(default_factory=list)