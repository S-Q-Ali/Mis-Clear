"""Security contract (SPEC-removal-flow): no confirm event -> no action, ever."""

from __future__ import annotations

import json
from collections import defaultdict, deque

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.backend.services.agent.registry import ToolSpec


def install_fakes(monkeypatch):
    import app.backend.api.agent as api

    class FakeBrain:
        def __init__(self, plan):
            self.plan = list(plan)

        def available(self):
            return True

        def complete(self, system, prompt):
            if self.plan:
                return self.plan.pop(0)
            return '{"thought":"done","stop":true,"answer":"final"}'

    def echo_tools(hybrid):
        def bounce(**kw):
            return {"ok": True, "note": "echo", "findings": [
                {"type": "search_hit", "title": "profile hit", "source": "s",
                 "url": "https://hit.example/x", "evidence": None,
                 "confidence": "probable", "severity": "medium",
                 "scope": "public", "matched": "my-alias"}]}

        return {
            "web_search": ToolSpec(
                name="web_search",
                description="offline echo",
                args={"target": {"type": "string", "description": "q", "required": True}},
                runner=bounce,
            )
        }

    monkeypatch.setattr(api, "_build_tools", echo_tools)
    return FakeBrain


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import app.backend.api.agent as api
    import app.backend.config as cfg
    import app.backend.database.engine as eng
    import app.backend.services.job_dispatcher as jd

    test_settings = cfg.Settings(
        database_path=str(tmp_path / "api.db"),
        ollama_url="",
        colab_ollama_url="",
        agent_enabled=True,
        agent_rate_limit_per_minute=100,
    )
    monkeypatch.setattr(cfg, "settings", test_settings)
    monkeypatch.setattr(eng, "settings", test_settings)
    monkeypatch.setattr(jd, "settings", test_settings)

    eng.engine = eng.build_engine(test_settings.database_path)
    eng.SessionLocal = sessionmaker(bind=eng.engine, autoflush=False, autocommit=False)
    eng.init_db()

    monkeypatch.setattr(api, "_rate_hits", defaultdict(deque))

    from app.backend.main import create_app

    with TestClient(create_app()) as c:
        yield c


def parse_sse(text):
    events = []
    current = None
    for line in text.splitlines():
        if line.startswith("event: "):
            current = line[len("event: "):]
        elif line.startswith("data: "):
            events.append((current, json.loads(line[len("data: "):])))
    return events


def run_chat(client, monkeypatch, message="find my profile"):
    import app.backend.api.agent as api

    FakeBrain = install_fakes(monkeypatch)
    monkeypatch.setattr(api, "_build_brain", lambda: FakeBrain([
        json.dumps({"thought": "search", "action": {"tool": "web_search", "args": {"target": "x"}}}),
        json.dumps({"thought": "done", "stop": True, "answer": "found one"}),
    ]))
    with client.stream("POST", "/api/agent/chat", json={"message": message}) as r:
        body = b"".join(r.iter_bytes()).decode("utf-8")
    return parse_sse(body)


def actions(client):
    return client.get("/api/actions?pageSize=100").json()["data"]


def test_no_action_until_confirm(client, monkeypatch):
    events = run_chat(client, monkeypatch)
    done = events[-1][1]
    assert done["confirmRequired"]
    assert actions(client) == []  # chat alone created nothing


def test_approve_creates_single_pending_action(client, monkeypatch):
    done = run_chat(client, monkeypatch)[-1][1]
    conv_id = done["conversationId"]
    r = client.post("/api/agent/confirm", json={
        "conversationId": conv_id, "itemIndex": 0, "decision": "approve"})
    assert r.status_code == 200
    action_id = r.json()["actionId"]
    assert action_id is not None

    lst = actions(client)
    assert len(lst) == 1
    a = lst[0]
    assert a["status"] == "pending"
    assert a["approvalRequired"] is True
    assert a["evidenceReference"] == f"agent:{conv_id}:https://hit.example/x"
    assert "hit.example" in a["instructions"]

    # same item again -> reuse, not duplicated
    r2 = client.post("/api/agent/confirm", json={
        "conversationId": conv_id, "itemIndex": 0, "decision": "approve"})
    assert r2.json()["actionId"] == action_id
    assert len(actions(client)) == 1


def test_deny_creates_no_action(client, monkeypatch):
    done = run_chat(client, monkeypatch)[-1][1]
    r = client.post("/api/agent/confirm", json={
        "conversationId": done["conversationId"], "itemIndex": 0, "decision": "deny"})
    assert r.status_code == 200
    assert r.json()["actionId"] is None
    assert actions(client) == []


def test_confirm_rejects_fabricated_item_index(client, monkeypatch):
    done = run_chat(client, monkeypatch)[-1][1]
    r = client.post("/api/agent/confirm", json={
        "conversationId": done["conversationId"], "itemIndex": 5, "decision": "approve"})
    assert r.status_code == 404
    assert actions(client) == []


def test_confirm_unknown_conversation(client, monkeypatch):
    r = client.post("/api/agent/confirm", json={
        "conversationId": 9999, "itemIndex": 0, "decision": "approve"})
    assert r.status_code == 404
    assert actions(client) == []


def test_confirm_bad_decision_rejected(client, monkeypatch):
    done = run_chat(client, monkeypatch)[-1][1]
    r = client.post("/api/agent/confirm", json={
        "conversationId": done["conversationId"], "itemIndex": 0, "decision": "maybe"})
    assert r.status_code == 422
    assert actions(client) == []