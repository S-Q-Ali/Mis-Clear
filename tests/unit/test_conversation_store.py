"""Conversation store redaction rules (SPEC-agent-api)."""

from __future__ import annotations

import json

from app.backend.services.agent.conversation_store import redact_step, redact_steps


def test_redact_tool_step_masks_secret_args():
    step = {"kind": "tool", "label": "breach_check",
            "detail": json.dumps({"passwords": ["hunter2"], "target": "me@x.dev"})}
    out = redact_step(step)
    assert out["detail"] == '{"passwords": "***", "target": "me@x.dev"}'


def test_redact_step_irrelevant_kinds_untouched():
    step = {"kind": "thought", "label": "thought", "detail": "plan"}
    assert redact_step(dict(step))["detail"] == "plan"


def test_redact_step_non_json_detail_untouched():
    step = {"kind": "tool", "label": "x", "detail": "not json"}
    assert redact_step(step)["detail"] == "not json"


def test_redact_steps_preserves_list_shape():
    steps = [
        {"kind": "thought", "detail": "a"},
        {"kind": "tool", "detail": json.dumps({"password": "hunter2"})},
    ]
    out = redact_steps(steps)
    assert len(out) == 2
    assert "hunter2" not in json.dumps(out)