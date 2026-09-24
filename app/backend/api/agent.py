"""Agent chat API (SPEC-agent-api): SSE streaming + persisted audit conversation.

Endpoint contract:
  POST /api/agent/chat  -> text/event-stream; events: start, thought, tool,
                           result, evidence, error, done.
  The run executes on a daemon thread and streams steps live through a queue so
  the browser sees progress instead of one blocking response.
"""

from __future__ import annotations

import json
import queue as queue_mod
import threading
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.backend.config import settings
from app.backend.database.engine import get_db
from app.backend.errors import api_error
from app.backend.schemas import (
    AgentChatIn,
    AgentConfirmIn,
    AgentConfirmOut,
    AgentMessageOut,
    AgentStatusOut,
    ConversationDetailOut,
    ConversationOut,
)
from app.backend.services.agent.brain import AgentBrain
from app.backend.services.agent.conversation_store import (
    create_conversation,
    get_conversation,
    list_conversations,
    save_agent_run,
)
from app.backend.services.agent.loop import run_agent
from app.backend.services.agent.model import AgentResult
from app.backend.services.agent.registry import build_agent_tools
from app.backend.services.agent.removal_flow import (
    action_from_proposal,
    confirm_proposals_of,
)

router = APIRouter(prefix="/api/agent", tags=["agent"])

_rate_hits: dict[str, deque[float]] = defaultdict(deque)


def _build_brain() -> AgentBrain:
    from app.backend.services.model_router import default_router

    return AgentBrain(router=default_router(), model=settings.agent_model or "")


def _build_tools(hybrid: bool) -> dict[str, Any]:
    from app.backend.services.model_router import default_router

    return build_agent_tools(
        router=default_router(),
        strict_local=not hybrid,
        hybrid_allowed=hybrid,
        breach_base_url=settings.breach_api_url or None,
    )


def _check_rate(key: str) -> None:
    limit = settings.agent_rate_limit_per_minute
    if limit <= 0:
        return
    now = time.monotonic()
    window = _rate_hits[key]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= limit:
        raise api_error(429, "RATE_LIMITED", "Too many agent requests; try again shortly.")
    window.append(now)


def _event(name: str, data: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps(data, default=str)}\n\n"


@router.get("/status")
def agent_status() -> AgentStatusOut:
    return AgentStatusOut(
        enabled=settings.agent_enabled,
        configured=bool(settings.colab_ollama_url or settings.ollama_url),
        backend=_build_brain().backend_name,
    )


@router.post("/chat")
def agent_chat(body: AgentChatIn, request: Request, db: Session = Depends(get_db)):
    key = request.client.host if request.client else "local"
    _check_rate(key)
    if not settings.agent_enabled:
        raise api_error(403, "AGENT_DISABLED", "Agent chat is disabled (PG_AGENT_ENABLED).")

    conv = create_conversation(
        db,
        title=body.message[:60],
        scan_id=body.scanId,
        hybrid_approved=body.approveHybrid,
    )
    tools = _build_tools(hybrid=body.approveHybrid)
    brain = _build_brain()
    q: queue_mod.Queue = queue_mod.Queue()
    box: dict[str, Any] = {}

    def run() -> None:
        try:
            result = run_agent(body.message, tools, brain, on_step=lambda step: q.put(step))
        except Exception as exc:  # noqa: BLE001 — API boundary: report, don't crash the stream
            result = AgentResult(
                blocked=True,
                answer=f"Agent failed: {exc.__class__.__name__}",
            )
        box["result"] = result
        q.put(None)

    threading.Thread(target=run, daemon=True).start()
    idle_timeout = max(10.0, float(settings.agent_step_timeout_seconds))

    def sse():
        yield _event("start", {"conversationId": conv.id})
        while True:
            try:
                item = q.get(timeout=idle_timeout)
            except queue_mod.Empty:
                yield _event("error", {"message": "agent run timed out"})
                break
            if item is None:
                break
            yield _event(item.kind, item.model_dump(mode="json"))
        result = box.get("result")
        if result is None:
            result = AgentResult(blocked=True, answer="Agent run did not return a result.")
        save_agent_run(db, conv.id, body.message, result)
        yield _event(
            "done",
            {
                "conversationId": conv.id,
                "answer": result.answer,
                "blocked": result.blocked,
                "confirmRequired": result.confirm_required,
            },
        )

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/conversations")
def conversations(db: Session = Depends(get_db)) -> list[ConversationOut]:
    return [ConversationOut.model_validate(c) for c in list_conversations(db)]


@router.get("/conversations/{conversation_id}")
def conversation_detail(conversation_id: int, db: Session = Depends(get_db)):
    conv = get_conversation(db, conversation_id)
    if conv is None:
        raise api_error(404, "NOT_FOUND", "Conversation not found")
    detail = ConversationDetailOut.model_validate(conv)
    detail.messages = [AgentMessageOut.model_validate(msg) for msg in conv.messages]
    return detail


@router.post("/confirm")
def agent_confirm(body: AgentConfirmIn, db: Session = Depends(get_db)):
    """Approve/deny one agent-proposed removal.

    Proposals are read back from the PERSISTED conversation steps — the client
    supplies only an index, never a URL. No confirm event -> no action.
    """
    from app.backend import models as m

    conv = get_conversation(db, body.conversationId)
    if conv is None:
        raise api_error(404, "NOT_FOUND", "Conversation not found")

    agent_messages = [msg for msg in conv.messages if msg.role == "agent"]
    if not agent_messages:
        raise api_error(409, "NO_AGENT_RUN", "Conversation has no agent run to confirm.")
    proposals = confirm_proposals_of(agent_messages[-1].steps)
    if not 0 <= body.itemIndex < len(proposals):
        raise api_error(404, "ITEM_NOT_FOUND", "That proposal is not in this conversation.")

    proposal = proposals[body.itemIndex]
    action_id: int | None = None
    if body.decision == "approve":
        action = action_from_proposal(db, conv.id, proposal)
        action_id = action.id
        db.add(
            m.AuditLog(
                actor="user",
                action="approve",
                entity_type="agent_removal",
                entity_id=action_id,
                detail=f"removal approved from conversation {conv.id}: {proposal['url']}",
            )
        )
    else:
        db.add(
            m.AuditLog(
                actor="user",
                action="deny",
                entity_type="agent_removal",
                entity_id=conv.id,
                detail=f"removal denied from conversation {conv.id}: {proposal['url']}",
            )
        )
    db.commit()
    return AgentConfirmOut(handled=True, actionId=action_id)