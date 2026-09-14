"""Job handler registry + built-in handlers (Phase 8; vision/OCR image transport Phase 15).

Every handler receives `(payload: dict, capabilities: CapabilityReport, client: httpx.Client | None) ->
dict`. Handlers must never fabricate AI results when no model backend is
available: missing model → explicit `{"ok": False, "note": "..."}`.

Built-in job types: `reasoning` (Ollama), `vision_analysis`, `ocr`, `barcode`,
`embeddings`. Vision/OCR carry the image as base64 in `payload["image_base64"]`
and hand it to Ollama via the native `images` parameter.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from colab.capabilities import CapabilityReport

HandlerFn = Callable[[dict[str, Any], CapabilityReport, "httpx.Client | None"], dict[str, Any]]

_REGISTRY: dict[str, HandlerFn] = {}

_VISION_DEFAULT = "gemma3:4b"
_OCR_PROMPT = (
    "Transcribe all visible text in this image verbatim, preserving order. "
    "If no text is visible, reply exactly: NO_TEXT."
)
_NSFW_PROMPT = (
    "You are a content-safety classifier, not an analyst. Classify the single "
    "image before you. Reply with exactly one JSON object, no prose:\n"
    '{"nsfw": bool, "category": "benign" | "adult" | "nudity" | "explicit" | '
    '"violence" | "gore", "confidence": float, "note": "one short honest sentence"}.\n'
    "Judge only what is actually visible. If nothing explicit is present, "
    "nsfw must be false and category 'benign'. Do not invent content."
)


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
    body: dict[str, Any] = {"model": model, "prompt": prompt, "stream": False}
    image_b64 = payload.get("image_base64")
    if image_b64:
        body["images"] = [image_b64]
    try:
        with (client if client is not None else httpx.Client(timeout=30)) as http:
            resp = http.post(f"{base_url.rstrip('/')}/api/generate", json=body)
            resp.raise_for_status()
            data = resp.json()
            return {"ok": True, "text": data.get("response", ""), "model": model}
    except httpx.HTTPError:
        return None


def _handle_reasoning(payload: dict[str, Any], caps: CapabilityReport, client: httpx.Client | None = None) -> dict[str, Any]:
    result = _ollama_generate(payload, base_url=payload.get("base_url", "http://127.0.0.1:11434"), client=client)
    if result is None:
        return {"ok": False, "note": "local Ollama not available"}
    return result


def _handle_vision(payload: dict[str, Any], caps: CapabilityReport, client: httpx.Client | None = None) -> dict[str, Any]:
    model = payload.get("model") or _VISION_DEFAULT
    if not caps.gpu and model not in caps.models:
        return {"ok": False, "note": "no vision model backend available", "model": model}
    result = _ollama_generate(
        {"prompt": payload.get("prompt", ""), "model": model, "image_base64": payload.get("image_base64")},
        base_url=payload.get("base_url", "http://127.0.0.1:11434"),
        client=client,
    )
    if result is None:
        return {"ok": False, "note": "vision backend unreachable", "model": model}
    return result


def _handle_ocr(payload: dict[str, Any], caps: CapabilityReport, client: httpx.Client | None = None) -> dict[str, Any]:
    if not caps.gpu:
        return {"ok": False, "note": "OCR requires GPU/colab worker"}
    model = payload.get("model", _VISION_DEFAULT)
    result = _ollama_generate(
        {"prompt": payload.get("prompt") or _OCR_PROMPT, "model": model, "image_base64": payload.get("image_base64")},
        base_url=payload.get("base_url", "http://127.0.0.1:11434"),
        client=client,
    )
    if result is None:
        return {"ok": False, "note": "OCR backend unreachable", "model": model}
    return result


def _handle_barcode(payload: dict[str, Any], caps: CapabilityReport, client: httpx.Client | None = None) -> dict[str, Any]:
    if not caps.gpu:
        return {"ok": False, "note": "barcode decoding requires vision backend (colab)"}
    return {"ok": False, "note": "barcode vision handler stub — dedicated decoder not wired"}


def _handle_nsfw(payload: dict[str, Any], caps: CapabilityReport, client: httpx.Client | None = None) -> dict[str, Any]:
    """Content-safety classification (Phase 16). Wording-only, never fabricated:
    classification is whatever the vision model returned, surfaced verbatim."""
    model = payload.get("model") or _VISION_DEFAULT
    if not caps.gpu and model not in caps.models:
        return {"ok": False, "note": "no NSFW-capable vision backend available", "model": model}
    result = _ollama_generate(
        {
            "prompt": payload.get("prompt") or _NSFW_PROMPT,
            "model": model,
            "image_base64": payload.get("image_base64"),
        },
        base_url=payload.get("base_url", "http://127.0.0.1:11434"),
        client=client,
    )
    if result is None:
        return {"ok": False, "note": "NSFW classification backend unreachable", "model": model}
    return result


_REMOVAL_DRAFT_PROMPT = (
    "You are refining a personal-data removal request DRAFT that a privacy "
    "assistant prepared. Rewrite it for clarity and professionalism. Hard rules:\n"
    "1. Keep every factual detail identical: the organization, URLs, dates, "
    "reference numbers, and the exact request being made.\n"
    "2. Do NOT add new URLs, new steps, invented facts, legal threats, or new "
    "organizations.\n"
    "3. Keep the final disclaimer line verbatim.\n"
    "Return only the rewritten draft.\n\n"
    "DRAFT:\n{text}"
)


def _handle_removal_draft(payload: dict[str, Any], caps: CapabilityReport, client: httpx.Client | None = None) -> dict[str, Any]:
    """Wording-only DRAFT refinement (Phase 16, slice 5). No new facts/URLs/steps;
    the laptop additionally post-checks URLs deterministically before storing."""
    text = (payload.get("text") or payload.get("draft") or "").strip()
    if not text:
        return {"ok": False, "note": "empty draft text supplied"}
    prompt = payload.get("prompt") or _REMOVAL_DRAFT_PROMPT.format(text=text)
    result = _ollama_generate(
        {"prompt": prompt, "model": payload.get("model") or "qwen3:8b"},
        base_url=payload.get("base_url", "http://127.0.0.1:11434"),
        client=client,
    )
    if result is None:
        return {"ok": False, "note": "draft-refinement backend unreachable"}
    return result


def _handle_embeddings(payload: dict[str, Any], caps: CapabilityReport, client: httpx.Client | None = None) -> dict[str, Any]:
    return {"ok": False, "note": "embedding service not yet wired"}


register_handler("reasoning", _handle_reasoning)
register_handler("vision_analysis", _handle_vision)
register_handler("ocr", _handle_ocr)
register_handler("barcode", _handle_barcode)
register_handler("embeddings", _handle_embeddings)
register_handler("nsfw_analysis", _handle_nsfw)
register_handler("removal_draft", _handle_removal_draft)