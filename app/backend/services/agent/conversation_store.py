"""Conversation persistence + audit for agent chat (SPEC-agent-api).

Secrets are redacted before anything touches the database: tool steps whose
args look like secrets (e.g. breach_check passwords) are written as `***`, and
outputs never contain plaintext by construction (k-anonymity prefixes only).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.backend.models import AgentConversation, AgentMessage, AuditLog
from app.backend.services.agent.model import AgentResult

SECRET_ARG_KEYS = {"password", "passwords", "secret", "token", "api_key", "apikey", "authorization"}


def redact_step(step: dict[str, Any]) -> dict[str, Any]:
    """Mask secret-looking args embedded in a `tool` step's detail JSON."""
    out = dict(step)
    if out.get("kind") != "tool":
        return out
    raw = out.get("detail")
    if not raw:
        return out
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return out
    if isinstance(parsed, dict):
        for key in list(parsed):
            if str(key).lower() in SECRET_ARG_KEYS:
                parsed[key] = "***"
        out["detail"] = json.dumps(parsed, sort_keys=True)
    return out


def redact_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [redact_step(s) for s in steps]


def create_conversation(
    db: Session,
    *,
    title: str = "Agent chat",
    scan_id: int | None = None,
    hybrid_approved: bool = False,
) -> AgentConversation:
    conv = AgentConversation(
        title=title,
        scan_id=scan_id,
        hybrid_approved=hybrid_approved,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def save_agent_run(db: Session, conversation_id: int, user_message: str, result: AgentResult) -> AgentMessage:
    """Persist one user turn + the full agent result (steps redacted)."""
    user_msg = AgentMessage(conversation_id=conversation_id, role="user", content=user_message)
    steps_json = redact_steps([s.model_dump(mode="json") for s in result.steps])
    agent_msg = AgentMessage(
        conversation_id=conversation_id,
        role="agent",
        content="",
        blocked=result.blocked,
        steps=steps_json,
        answer=result.answer,
    )
    db.add_all([user_msg, agent_msg])

    conv = db.get(AgentConversation, conversation_id)
    if conv is not None:
        if result.blocked:
            conv.status = "blocked"
        elif any(s.kind == "error" for s in result.steps):
            conv.status = "error"
        else:
            conv.status = "complete"

        conv.updated_at = datetime.now(UTC)
        db.add(conv)
        if conv.hybrid_approved:
            db.add(
                AuditLog(
                    actor="user",
                    action="approve",
                    entity_type="agent_hybrid",
                    entity_id=conv.id,
                    detail="hybrid tools approved for an agent chat run",
                )
            )
    db.commit()
    db.refresh(agent_msg)
    return agent_msg


def list_conversations(db: Session, limit: int = 50) -> list[AgentConversation]:
    return (
        db.query(AgentConversation)
        .order_by(AgentConversation.created_at.desc())
        .limit(limit)
        .all()
    )


def get_conversation(db: Session, conversation_id: int) -> AgentConversation | None:
    return db.get(AgentConversation, conversation_id)