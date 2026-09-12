"""Phase 8: worker handler registry tests (synthetic, no real Ollama)."""

from __future__ import annotations

import httpx
import pytest

from colab.capabilities import CapabilityReport
from colab.handlers import (
    _REGISTRY,
    _ollama_generate,
    get_handler,
    register_handler,
)


def test_registry_register_and_get():
    def fake(payload, caps):  # noqa: ARG001
        return {"ok": True}

    register_handler("zz_test", fake)
    assert get_handler("zz_test") is fake
    with pytest.raises(ValueError):
        register_handler("", fake)
    with pytest.raises(ValueError):
        register_handler("zz_bad", "not-callable")  # type: ignore[arg-type]


def test_builtin_job_types_registered():
    for name in ("reasoning", "vision_analysis", "ocr", "barcode", "embeddings"):
        assert get_handler(name) is not None


def _caps(gpu: bool = False, models=None):
    return CapabilityReport(gpu=gpu, models=models or [])


def test_reasoning_degrades_without_ollama(monkeypatch):
    monkeypatch.setattr("colab.handlers._ollama_generate", lambda _p, **k: None)
    res = get_handler("reasoning")({"prompt": "hi"}, _caps())
    assert res["ok"] is False and "not available" in res["note"]


def test_vision_degrades_without_gpu_and_model(monkeypatch):
    assert get_handler("vision_analysis")({"prompt": "x"}, _caps(gpu=False))["ok"] is False


def test_barcode_and_embeddings_honest_stubs():
    assert get_handler("barcode")({}, _caps(gpu=True))["ok"] is False
    assert get_handler("embeddings")({}, _caps())["ok"] is False


def test_ollama_generate_succeeds_with_mock_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "hello from fake ollama"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    res = _ollama_generate({"prompt": "hello"}, client=client)
    assert res["ok"] is True
    assert res["text"] == "hello from fake ollama"
    assert res["model"] == "qwen3:8b"


def test_ollama_generate_http_error_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        raise httpx.ConnectError("down")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    res = _ollama_generate({"prompt": "hi"}, client=client)
    assert res is None