"""Agent chat API integration tests (SPEC-agent-api). Isolated SQLite + fake brain."""

from __future__ import annotations

import json
from collections import defaultdict, deque

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.backend.services.agent.registry import ToolSpec


def install_fakes(monkeypatch):
    """Deterministic brain + offline tools for every chat test."""
    import app.backend.api.agent as api

    class FakeBrain:
        def __init__(self, plan):
            self.plan = list(plan)
            self.available_flag = True

        def available(self):
            return self.available_flag

        def complete(self, system, prompt):
            if self.plan:
                return self.plan.pop(0)
            return '{"thought":"done","stop":true,"answer":"final"}'

    def make_echo_tools(hybrid: bool):
        def bounce(**kw):
            return {"ok": True, "note": "echo", "findings": [
                {"type": "search_hit", "title": "h", "source": "s",
                 "url": "https://hit.example/x", "evidence": None,
                 "confidence": "weak", "severity": "low", "scope": "public"}]}

        return {
            "web_search": ToolSpec(
                name="web_search",
                description="offline echo",
                args={"target": {"type": "string", "description": "q", "required": True}},
                runner=bounce,
            )
        }

    monkeypatch.setattr(api, "_build_tools", make_echo_tools)
    return monkeypatch, FakeBrain


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


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("event: "):
            current = line[len("event: "):]
        elif line.startswith("data: "):
            events.append((current or "", json.loads(line[len("data: "):])))
    return events


def test_status_endpoint(client):
    r = client.get("/api/agent/status")
    assert r.status_code == 200
    assert r.json()["enabled"] is True
    assert r.json()["backend"] == "none"
    assert r.json()["model"] == "qwen3:8b"


def test_status_model_mirrors_agent_model_override(client, monkeypatch):
    """PG_AGENT_MODEL override must be surfaced so the 27B brain is verifiable."""
    import app.backend.api.agent as api
    import app.backend.config as cfg

    cfg.settings.agent_model = "hf.co/JonathanColetti/Qwen3.8-27B-Uncensored-GGUF:Q4_K_M"
    monkeypatch.setattr(api, "settings", cfg.settings)
    r = client.get("/api/agent/status")
    assert r.status_code == 200
    assert r.json()["model"] == cfg.settings.agent_model


def test_chat_stream_stop_immediately(client, monkeypatch):
    import app.backend.api.agent as api

    _, FakeBrain = install_fakes(monkeypatch)
    monkeypatch.setattr(
        api,
        "_build_brain",
        lambda: FakeBrain([json.dumps({"thought": "enough", "stop": True, "answer": "hi"})]),
    )
    with client.stream("POST", "/api/agent/chat", json={"message": "hello"}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = b"".join(r.iter_bytes()).decode("utf-8")
    events = parse_sse(body)
    kinds = [k for k, _ in events]
    assert kinds[0] == "start"
    assert "thought" in kinds
    assert kinds[-1] == "done"
    done = events[-1][1]
    assert done["answer"] == "hi"
    assert done["blocked"] is False


def test_chat_stream_emits_tool_and_evidence(client, monkeypatch):
    import app.backend.api.agent as api

    _, FakeBrain = install_fakes(monkeypatch)
    monkeypatch.setattr(api, "_build_brain", lambda: FakeBrain([
        json.dumps({"thought": "search", "action": {"tool": "web_search", "args": {"target": "a@x.dev"}}}),
        json.dumps({"thought": "done", "stop": True, "answer": "one hit"}),
    ]))
    with client.stream("POST", "/api/agent/chat", json={"message": "trace"}) as r:
        body = b"".join(r.iter_bytes()).decode("utf-8")
    events = parse_sse(body)
    kinds = [k for k, _ in events]
    assert "tool" in kinds and "result" in kinds
    result = next(d for k, d in events if k == "result")
    assert result["evidence"] == ["https://hit.example/x"]
    assert sum(1 for k, _ in events if k == "error") == 0


def test_chat_blocked_when_brain_unavailable(client, monkeypatch):
    import app.backend.api.agent as api

    _, FakeBrain = install_fakes(monkeypatch)

    class NoBrain(FakeBrain):
        def available(self):
            return False

    monkeypatch.setattr(api, "_build_brain", lambda: NoBrain([]))
    with client.stream("POST", "/api/agent/chat", json={"message": "x"}) as r:
        body = b"".join(r.iter_bytes()).decode("utf-8")
    events = parse_sse(body)
    done = events[-1][1]
    assert done["blocked"] is True


def test_chat_disabled_returns_403(client, monkeypatch):
    import app.backend.api.agent as api

    monkeypatch.setattr(api.settings, "agent_enabled", False)
    r = client.post("/api/agent/chat", json={"message": "x"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "AGENT_DISABLED"


def test_chat_rate_limited(client, monkeypatch):
    import app.backend.api.agent as api

    monkeypatch.setattr(api.settings, "agent_rate_limit_per_minute", 3)
    monkeypatch.setattr(api, "_rate_hits", defaultdict(deque))

    _, FakeBrain = install_fakes(monkeypatch)
    monkeypatch.setattr(api, "_build_brain", lambda: FakeBrain(
        [json.dumps({"thought": "done", "stop": True, "answer": "ok"})]
    ))
    for i in range(3):
        with client.stream("POST", "/api/agent/chat", json={"message": f"m{i}"}) as r:
            body = b"".join(r.iter_bytes()).decode("utf-8")
        assert parse_sse(body)[-1][0] == "done"
    # 4th should be rejected synchronously
    r = client.post("/api/agent/chat", json={"message": "m4"})
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "RATE_LIMITED"


def test_conversation_persists_and_redacts_secrets(client, monkeypatch):
    import app.backend.api.agent as api

    _, FakeBrain = install_fakes(monkeypatch)

    # brain that calls breach_check-style tool with a secret arg
    def secret_tools(hybrid: bool):
        def leaky(**kw):
            return {"ok": True, "note": "checked", "items": [
                {"password_sha1_prefix": "ABCDE", "suffix_matches": 9, "breached": True}]}

        return {
            "breach_check": ToolSpec(
                name="breach_check",
                description="offline breach",
                args={"passwords": {"type": "list", "description": "pws", "required": True}},
                runner=leaky,
            )
        }

    monkeypatch.setattr(api, "_build_tools", secret_tools)
    monkeypatch.setattr(api, "_build_brain", lambda: FakeBrain([
        json.dumps({"thought": "check", "action": {"tool": "breach_check", "args": {"passwords": ["hunter2", "pw2"]}}}),
        json.dumps({"thought": "done", "stop": True, "answer": "one breached"}),
    ]))
    with client.stream("POST", "/api/agent/chat", json={"message": "check pws", "approveHybrid": True}) as r:
        body = b"".join(r.iter_bytes()).decode("utf-8")
    events = parse_sse(body)
    done = events[-1][1]
    conv_id = done["conversationId"]

    detail = client.get(f"/api/agent/conversations/{conv_id}").json()
    assert detail["hybridApproved"] is True
    tool_step: dict | None = None
    for msg in detail["messages"]:
        for step in msg.get("steps") or []:
            if step.get("kind") == "tool":
                tool_step = step
    assert tool_step is not None
    assert "hunter2" not in json.dumps(tool_step)
    assert "pw2" not in json.dumps(tool_step)
    assert "***" in json.dumps(tool_step)

    lst = client.get("/api/agent/conversations").json()
    assert len(lst) == 1
    assert lst[0]["status"] == "complete"


def test_conversation_not_found(client):
    assert client.get("/api/agent/conversations/9999").status_code == 404