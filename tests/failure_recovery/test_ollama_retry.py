"""Phase 14 failure/recovery: Ollama backend retry behaviour.

Deterministic failure injection: monkeypatch the httpx.Client factory inside
model_router so the backend's own `generate()` retry loop runs against a
MockTransport. Sleep is patched out so tests stay fast and deterministic.
"""

from __future__ import annotations

import httpx
import pytest

import app.backend.services.model_router as mr
from app.backend.services.model_router import ModelUnavailableError, OllamaBackend


def _patch_http(monkeypatch, handler):
    real_client = httpx.Client

    def _factory(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(mr.httpx, "Client", _factory)


def _backend(retries: int) -> OllamaBackend:
    return OllamaBackend("local-ollama", "https://ollama.test", "q", timeout=5, retries=retries)


def test_transient_failure_then_success_recovers(monkeypatch):
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request.url.path)
        if len(attempts) == 1:
            raise httpx.ConnectError("transient")
        return httpx.Response(200, json={"model": "q", "response": "recovered", "done": True})

    _patch_http(monkeypatch, handler)
    backend = _backend(retries=2)
    monkeypatch.setattr("time.sleep", lambda _: None)

    response = backend.generate("hi")
    assert response.text == "recovered"
    assert response.backend == "local-ollama"
    assert len(attempts) == 2


def test_persistent_failure_exhausts_retries_then_clean_error(monkeypatch):
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request.url.path)
        return httpx.Response(500, json={"error": "model busy"})

    _patch_http(monkeypatch, handler)
    backend = _backend(retries=3)
    monkeypatch.setattr("time.sleep", lambda _: None)

    with pytest.raises(ModelUnavailableError, match="inference failed"):
        backend.generate("hi")
    assert len(attempts) == 4  # retries + 1 initial attempt, never swallowed


def test_successful_attempt_does_not_retry(monkeypatch):
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request.url.path)
        return httpx.Response(200, json={"model": "q", "response": "ok", "done": True})

    _patch_http(monkeypatch, handler)
    backend = _backend(retries=5)
    assert backend.generate("hi").text == "ok"
    assert len(attempts) == 1