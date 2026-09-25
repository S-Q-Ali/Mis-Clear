"""Agent core loop contract (SPEC-agent-core)."""

from __future__ import annotations

import json

from app.backend.services.agent.loop import (
    SYSTEM_PROMPT,
    parse_action,
    run_agent,
    validate_args,
)
from app.backend.services.agent.model import AgentAction
from app.backend.services.agent.registry import ToolSpec


def make_tool(name: str = "dns", runner=None, args=None):
    def default_runner(**kw):
        return {"ok": True, "note": "resolved", "findings": []}

    spec = ToolSpec(
        name=name,
        description="test tool",
        args=args or {"target": {"type": "string", "description": "x", "required": True}},
        runner=runner or default_runner,
    )
    return spec


class FakeBrain:
    def __init__(self, responses: list[str], available: bool = True):
        self._responses = list(responses)
        self.available_flag = available
        self.calls: list[tuple[str, str]] = []

    def available(self) -> bool:
        return self.available_flag

    def complete(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        if self._responses:
            return self._responses.pop(0)
        return '{"thought":"done","stop":true,"answer":"final"}'


def act(**kw) -> str:
    return json.dumps(kw)


# --- parse_action ----------------------------------------------------------


def test_parse_action_strict_json():
    parsed = parse_action('{"thought":"think","action":{"tool":"dns","args":{"target":"x.dev"}},"stop":false,"answer":""}')
    assert isinstance(parsed, AgentAction)
    assert parsed.action is not None and parsed.action.tool == "dns"


def test_parse_action_recovers_json_from_noise():
    parsed = parse_action('Sure! Here it is\n{"thought":"hi","stop":true,"answer":"yo"} trailing')
    assert parsed is not None and parsed.stop and parsed.answer == "yo"


def test_parse_action_rejects_non_json():
    assert parse_action("I have no JSON for you") is None
    assert parse_action("") is None
    assert parse_action("not json { broken") is None


# --- validate_args ---------------------------------------------------------


def test_validate_args_filters_unknown_and_requires_required():
    spec = make_tool()
    assert validate_args(spec, {"target": "a.dev", "evil": "shell --rm"}) == {"target": "a.dev"}
    assert validate_args(spec, {"evil": "x"}) is None
    assert validate_args(spec, None) is None


# --- run_agent loop --------------------------------------------------------


def test_immediate_stop_returns_answer_no_tools():
    brain = FakeBrain([act(thought="done", stop=True, answer="found nothing")])
    result = run_agent("find my email traces", {"dns": make_tool()}, brain)
    assert result.blocked is False
    assert result.answer == "found nothing"
    assert [s.kind for s in result.steps] == ["thought", "thought"]


def test_single_tool_then_stop_emits_tool_and_result():
    calls: list[dict] = []

    def capture(**kw):
        calls.append(kw)
        return {"ok": True, "note": "2 hits",
                "findings": [{"type": "search_hit", "title": "t", "source": "s",
                              "url": "https://e.example/x", "evidence": None,
                              "confidence": "weak", "severity": "low", "scope": "public"}]}

    tools = {"web_search": make_tool("web_search", runner=capture)}
    brain = FakeBrain([
        act(thought="search first", action={"tool": "web_search", "args": {"target": "me@x.com"}}),
        act(thought="enough", stop=True, answer="found 1"),
    ])
    result = run_agent("trace it", tools, brain)
    kinds = [s.kind for s in result.steps]
    assert kinds[:3] == ["thought", "tool", "result"]
    assert kinds.count("thought") == 3
    assert result.answer == "found 1"
    assert calls == [{"target": "me@x.com"}]
    tool_step = next(s for s in result.steps if s.kind == "result")
    assert tool_step.evidence == ["https://e.example/x"]


def test_unknown_tool_is_rejected():
    brain = FakeBrain([
        act(thought="run it", action={"tool": "shell", "args": {}}),
    ])
    result = run_agent("go", {"dns": make_tool()}, brain)
    assert result.answer == "Agent stopped: 'shell' is not an allowed tool."
    assert any(s.kind == "error" for s in result.steps)
    assert not any(s.kind == "tool" for s in result.steps)


def test_missing_required_arg_stops():
    brain = FakeBrain([
        act(thought="probe", action={"tool": "dns", "args": {}}),
    ])
    result = run_agent("resolve", {"dns": make_tool()}, brain)
    assert "invalid arguments" in result.answer


def test_brain_unavailable_blocks_gracefully():
    brain = FakeBrain([], available=False)
    result = run_agent("trace", {"dns": make_tool()}, brain)
    assert result.blocked is True
    assert result.steps[0].kind == "error"


def test_step_budget_exhausted_terminates():
    calls: list[int] = []

    def forever(**kw):
        calls.append(1)
        return {"ok": True, "note": "again", "findings": []}

    brain = FakeBrain(
        [act(thought=f"loop {i}", action={"tool": "dns", "args": {"target": "x.dev"}}) for i in range(10)]
    )
    result = run_agent("loop", {"dns": make_tool(runner=forever)}, brain, max_steps=3)
    assert result.answer == "Agent stopped: step budget exhausted."
    assert len(calls) == 3
    assert sum(s.kind == "result" for s in result.steps) == 3


def test_parse_failure_stops_cleanly():
    brain = FakeBrain(["I cannot comply {broken"])
    result = run_agent("go", {"dns": make_tool()}, brain)
    assert any(s.kind == "error" for s in result.steps)
    assert "cannot parse" in result.answer


def test_brain_failure_stops_cleanly():
    class ExplodingBrain:
        def available(self):
            return True

        def complete(self, system, prompt):
            raise RuntimeError("boom")

    result = run_agent("go", {"dns": make_tool()}, ExplodingBrain())
    assert any(s.kind == "error" for s in result.steps)
    assert "stopped early" in result.answer


def test_empty_goal():
    result = run_agent("", {"dns": make_tool()}, FakeBrain([]))
    assert result.steps[0].kind == "error"


def test_system_prompt_contains_untrusted_rule():
    brain = FakeBrain([], available=True)
    run_agent("x", {"dns": make_tool()}, brain, max_steps=1)
    system, _prompt = brain.calls[0]
    assert "<untrusted>" in SYSTEM_PROMPT or "untrusted" in system
    assert "Reply with exactly ONE JSON object" in system


def test_system_prompt_lists_available_tools():
    tools = {
        "dns": make_tool("dns"),
        "web_search": make_tool("web_search"),
    }
    brain = FakeBrain([], available=True)
    run_agent("x", tools, brain, max_steps=1)
    system, _prompt = brain.calls[0]
    assert "- dns(target):" in system
    assert "- web_search(target):" in system
    assert "shell(" not in system