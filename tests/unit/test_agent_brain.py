"""AgentBrain model routing contract (SPEC-agent-core / uncensored brain).

The configured agent model name must reach the Ollama backend VERBATIM — the
uncensored brain is `qwen3.8-27b-unc` on the Colab Ollama, and any silent
rewriting would either leak the request to the wrong model or fail the call.
Empty model keeps the backend default (backward compatible). No backend -> hard
ModelUnavailableError, never a fabricated answer.
"""

from __future__ import annotations

import pytest

from app.backend.services import model_router
from app.backend.services.agent.brain import AgentBrain
from app.backend.services.model_router import (
    ModelResponse,
    ModelUnavailableError,
    OllamaBackend,
)

MODEL_UNCENSORED = "qwen3.8-27b-unc"


class _StubRouter:
    """Deterministic router: returns the same backend (or None) every route()."""

    def __init__(self, backend) -> None:
        self._backend = backend

    def route(self, strict_local: bool = False):
        return self._backend


def _capture_generate(monkeypatch) -> dict:
    """Stub OllamaBackend.generate to record self.model + kwargs instead of HTTP."""
    captured: dict = {}

    def fake_generate(self, prompt, system=None, **kwargs):
        captured["model"] = self.model
        captured["kwargs"] = kwargs
        return ModelResponse(text="ok", model=self.model, backend=self.name, duration_ms=1)

    monkeypatch.setattr(model_router.OllamaBackend, "generate", fake_generate)
    return captured


def test_brain_forwards_configured_model_verbatim(monkeypatch):
    captured = _capture_generate(monkeypatch)
    backend = OllamaBackend("colab-ollama", "http://127.0.0.1:11434", model="qwen3:8b")
    brain = AgentBrain(router=_StubRouter(backend), model=MODEL_UNCENSORED)
    out = brain.complete("system", "prompt")

    assert captured["model"] == MODEL_UNCENSORED
    assert out == "ok"


def test_brain_empty_model_keeps_backend_default(monkeypatch):
    captured = _capture_generate(monkeypatch)
    backend = OllamaBackend("colab-ollama", "http://127.0.0.1:11434", model="qwen3:8b")
    brain = AgentBrain(router=_StubRouter(backend), model="")
    brain.complete("system", "prompt")
    assert captured["model"] == "qwen3:8b"


def test_brain_no_backend_raises_unavailable():
    brain = AgentBrain(router=_StubRouter(backend=None), model=MODEL_UNCENSORED)
    with pytest.raises(ModelUnavailableError):
        brain.complete("system", "prompt")


def test_brain_forces_strict_json_output(monkeypatch):
    captured = _capture_generate(monkeypatch)
    backend = OllamaBackend("colab-ollama", "http://127.0.0.1:11434", model="qwen3:8b")
    brain = AgentBrain(router=_StubRouter(backend), model="")
    brain.complete("system", "prompt")
    assert captured["kwargs"].get("format") == "json"