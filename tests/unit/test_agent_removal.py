"""Confirm-gated removal proposals (SPEC-removal-flow): deterministic, never AI."""

from __future__ import annotations

import json

from app.backend.services.agent.loop import propose_removals, run_agent
from app.backend.services.agent.registry import ToolSpec


def make_tool(runner=None):
    def default_runner(**kw):
        return {"ok": True, "note": "resolved", "findings": []}

    return ToolSpec(
        name="dns",
        description="test tool",
        args={"target": {"type": "string", "description": "x", "required": True}},
        runner=runner or default_runner,
    )


class FakeBrain:
    def __init__(self, responses, available=True):
        self._responses = list(responses)
        self.available_flag = available

    def available(self):
        return self.available_flag

    def complete(self, system, prompt):
        if self._responses:
            return self._responses.pop(0)
        return '{"thought":"done","stop":true,"answer":"final"}'


def act(**kw):
    return json.dumps(kw)


def prop(**kw):
    f = kw.get("finding", {})
    entry = {"type": "search_hit", "title": "t", "source": "s",
             "url": "https://hit.example/p", "evidence": None,
             "confidence": "weak", "severity": "low", "scope": "public"}
    entry.update(f)
    out = {"ok": True, "note": "x", "findings": [entry]}
    out.update(kw.get("extra", {}))
    return out


def test_propose_removals_only_url_findings():
    out = {
        "ok": True,
        "findings": [
            {"url": "https://a.example/x", "title": "a"},
            {"title": "no url"},
            {"detail": "not a finding"},
        ],
    }
    props = propose_removals(out)
    assert len(props) == 1
    assert props[0]["url"] == "https://a.example/x"
    assert props[0]["org"] == "a.example"
    assert props[0]["evidence"] == "https://a.example/x"


def test_propose_removals_skips_localhost():
    props = propose_removals(
        {"ok": True, "findings": [{"url": "http://127.0.0.1/x"}, {"url": "http://localhost/x"}]}
    )
    assert props == []


def test_propose_removals_empty_outputs():
    assert propose_removals({}) == []
    assert propose_removals({"findings": []}) == []
    assert propose_removals({"findings": None}) == []


def test_loop_emits_confirm_steps_for_url_findings():
    def hit(**kw):
        return prop()

    brain = FakeBrain([
        act(thought="probe", action={"tool": "dns", "args": {"target": "x.dev"}}),
        act(thought="enough", stop=True, answer="found"),
    ])
    result = run_agent("trace", {"dns": make_tool(runner=hit)}, brain)
    confirms = [s for s in result.steps if s.kind == "confirm"]
    assert len(confirms) == 1
    step = confirms[0]
    assert step.data["url"] == "https://hit.example/p"
    assert step.data["org"] == "hit.example"
    assert step.evidence == ["https://hit.example/p"]
    assert result.confirm_required == [str(result.steps.index(step))]


def test_loop_no_confirm_without_url_findings():
    results: list[dict] = []

    def empty(**kw):
        results.append(kw)
        return {"ok": True, "note": "none", "findings": []}

    brain = FakeBrain([
        act(thought="probe", action={"tool": "dns", "args": {"target": "x.dev"}}),
        act(thought="enough", stop=True, answer="clean"),
    ])
    result = run_agent("trace", {"dns": make_tool(runner=empty)}, brain)
    assert sum(s.kind == "confirm" for s in result.steps) == 0
    assert result.confirm_required == []


def test_loop_multiple_urls_many_confirms_indexed():
    def many(**kw):
        return prop(extra={"findings": [
            {"url": "https://one.example/a", "title": "a"},
            {"url": "https://two.example/b", "title": "b"},
        ]})

    brain = FakeBrain([
        act(thought="probe", action={"tool": "dns", "args": {"target": "x.dev"}}),
        act(thought="enough", stop=True, answer="two"),
    ])
    result = run_agent("trace", {"dns": make_tool(runner=many)}, brain)
    confirms = [s for s in result.steps if s.kind == "confirm"]
    assert len(confirms) == 2
    indexes = [result.steps.index(s) for s in confirms]
    assert result.confirm_required == [str(i) for i in indexes]
    assert confirms[0].data["org"] == "one.example"
    assert confirms[1].data["org"] == "two.example"