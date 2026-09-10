"""ModelRouter: deterministic routing, approval gating, graceful failure."""

import httpx
import pytest

from app.backend.services.model_router import (
    ModelRouter,
    ModelResponse,
    ModelUnavailableError,
    OllamaBackend,
)


class FakeBackend:
    def __init__(self, name: str, available: bool = True):
        self.name = name
        self._available = available

    def available(self) -> bool:
        return self._available

    def generate(self, prompt: str, system: str | None = None, **kwargs):
        return ModelResponse(text=f"{self.name}:{prompt}", model="x", backend=self.name, duration_ms=1)


def test_routes_to_colab_when_approved_and_available():
    router = ModelRouter(local=FakeBackend("local"), colab=FakeBackend("colab"), colab_approved=True)
    assert router.route().name == "colab"


def test_skips_unapproved_colab():
    router = ModelRouter(local=FakeBackend("local"), colab=FakeBackend("colab"), colab_approved=False)
    assert router.route().name == "local"


def test_falls_back_to_local_when_colab_unavailable():
    router = ModelRouter(
        local=FakeBackend("local"), colab=FakeBackend("colab", available=False), colab_approved=True
    )
    assert router.route().name == "local"


def test_local_only_never_uses_colab():
    router = ModelRouter(local=FakeBackend("local"), colab=FakeBackend("colab"), colab_approved=True)
    assert router.route(strict_local=True).name == "local"


def test_none_when_everything_down():
    router = ModelRouter(local=FakeBackend("local", available=False), colab=FakeBackend("colab", available=False))
    assert router.route() is None


def test_generate_raises_clean_when_no_backend():
    router = ModelRouter(local=None, colab=None, colab_approved=True)
    with pytest.raises(ModelUnavailableError):
        router.generate("hi")


def _mock_transport(status: int, body: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body, request=request)

    return httpx.MockTransport(handler)


def test_ollama_available_via_tags_endpoint():
    backend = OllamaBackend("t", "http://ollama:11434", "m", timeout=2, retries=0)
    client = httpx.Client(transport=_mock_transport(200, {"models": []}))
    resp = client.get(f"{backend.base_url}/api/tags")
    assert resp.status_code == 200
    assert resp.json() == {"models": []}


def test_ollama_generate_parses_response():
    backend = OllamaBackend("t", "http://ollama:11434", "m", timeout=2, retries=0)
    client = httpx.Client(transport=_mock_transport(200, {"response": "hello", "done": True}))
    resp = client.post(f"{backend.base_url}/api/generate", json={"model": "m", "prompt": "p", "stream": False})
    data = resp.json()
    assert data["response"] == "hello"


def test_ollama_generate_raises_on_http_error():
    backend = OllamaBackend("t", "http://ollama:11434", "m", timeout=2, retries=0)
    client = httpx.Client(transport=_mock_transport(503, {"error": "overloaded"}))
    resp = client.post(f"{backend.base_url}/api/generate", json={"model": "m", "prompt": "p", "stream": False})
    assert resp.status_code == 503


def test_default_router_has_local_backend_only_without_colab_url(monkeypatch):
    from app.backend.config import Settings

    monkeypatch.setattr(
        "app.backend.services.model_router.settings",
        Settings(
            ollama_url="http://127.0.0.1:11434",
            colab_ollama_url="",
            hybrid_requires_explicit_approval=True,
        ),
    )
    from app.backend.services import model_router

    router = model_router.default_router()
    assert router.local is not None
    assert router.colab is None