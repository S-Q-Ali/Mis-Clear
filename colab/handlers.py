"""Job handler registry + built-in synthetic handlers (Phase 8).

Every handler receives `(payload: dict, capabilities: CapabilityReport) -> dict`.
Handlers must never fabricate AI results when no model backend is available:
missing model → explicit `{"ok": False, "note": "model not available"}`.

Built-in job types: `reasoning` (Ollama), `vision_analysis`, `ocr`, `barcode`,
`embeddings`. Actual GPU/colab backend usage wired in later phase.
"""

from __future__ import annotations

from typing import Any, Callable

import httpx

from colab.capabilities import CapabilityReport

HandlerFn = Callable[[dict[str, Any], CapabilityReport], dict[str, Any]]

_REGISTRY: dict[str, HandlerFn] = {}


def register_handler(job_type: str, fn: HandlerFn) -> None:
    if not job_type or not callable(fn):
        raise ValueError("job_type and callable fn required")
    _REGISTRY[job_type] = fn


def get_handler(job_type: str) -> HandlerFn | None:
    return _REGISTRY.get(job_type)


def _ollama_generate(
    payload: dict[str, Any],
    *,
    base_url: str = "http://127.0.0.1:11434",
    client: httpx.Client | None = None,
) -> dict[str, Any] | None:
    prompt = payload.get("prompt") or payload.get("query") or ""
    model = payload.get("model") or "qwen3:8b"
    if not prompt:
        return {"ok": False, "note": "empty prompt"}
    try:
        with (client if client is not None else httpx.Client(timeout=30)) as http:
            resp = http.post(
                f"{base_url.rstrip('/')}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
            )
            resp.raise_for_status()
            data = resp.json()
            return {"ok": True, "text": data.get("response", ""), "model": model}
    except httpx.HTTPError:
        return None


def _handle_reasoning(payload: dict[str, Any], caps: CapabilityReport) -> dict[str, Any]:
    result = _ollama_generate(payload, base_url=payload.get("base_url", "http://127.0.0.1:11434"))
    if result is None:
        return {"ok": False, "note": "local Ollama not available"}
    return result


def _handle_vision(payload: dict[str, Any], caps: CapabilityReport) -> dict[str, Any]:
    model = payload.get("model") or "gemma3:4b"
    if not caps.gpu and model not in caps.models:
        return {"ok": False, "note": "no vision model backend available", "model": model}
    return _ollama_generate({"prompt": payload.get("prompt", ""), "model": model}) or {"ok": False, "note": "vision backend unreachable"}


def _handle_ocr(payload: dict[str, Any], caps: CapabilityReport) -> dict[str, Any]:
    if not caps.gpu:
        return {"ok": False, "note": "OCR requires GPU/colab worker"}
    return _handle_vision({"prompt": payload.get("prompt", ""), "model": payload.get("model", "gemma3:4b")}, caps)


def _handle_barcode(payload: dict[str, Any], caps: CapabilityReport) -> dict[str, Any]:
    if not caps.gpu:
        return {"ok": False, "note": "barcode decoding requires vision backend (colab)"}
    return {"ok": False, "note": "barcode vision handler stub"}


def _handle_embeddings(payload: dict[str, Any], caps: CapabilityReport) -> dict[str, Any]:
    return {"ok": False, "note": "embedding service not yet wired"}


register_handler("reasoning", _handle_reasoning)
register_handler("vision_analysis", _handle_vision)
register_handler("ocr", _handle_ocr)
register_handler("barcode", _handle_barcode)
register_handler("embeddings", _handle_embeddings)