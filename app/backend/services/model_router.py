"""ModelRouter: route AI inference to an available backend.

Routing priority (deterministic):
    1. Colab Ollama (only when user-approved AND available)
    2. Local Ollama (when available)
    3. Task queue / graceful failure (never blocks the app)

Mode control:
    - strict_local=True ("LOCAL ONLY"): never use Colab; sensitive data stays
      on the laptop regardless of approval.
    - default: Colab may be used only when explicitly approved.
    - OFFLINE: no network AI; router raises ModelUnavailableError cleanly.

Zero external AI is fine: if no backend is available the app still works;
callers degrade gracefully instead of crashing.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.backend.config import settings


class ModelUnavailableError(RuntimeError):
    """Raised when no AI backend can serve the request."""


@dataclass
class ModelResponse:
    text: str
    model: str
    backend: str
    duration_ms: int
    raw: dict[str, Any] = field(default_factory=dict)


class InferenceBackend(Protocol):
    name: str

    def available(self) -> bool: ...

    def generate(self, prompt: str, system: str | None = None, **kwargs: Any) -> ModelResponse: ...


class OllamaBackend:
    """HTTP backend for any Ollama server (local or Colab/site tunnel)."""

    def __init__(
        self,
        name: str,
        base_url: str,
        model: str,
        timeout: int | None = None,
        retries: int | None = None,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout if timeout is not None else settings.ollama_timeout_seconds
        self.retries = retries if retries is not None else settings.ollama_retries

    def available(self) -> bool:
        try:
            with httpx.Client(timeout=5) as client:
                return client.get(f"{self.base_url}/api/tags").status_code == 200
        except httpx.HTTPError:
            return False

    def generate(self, prompt: str, system: str | None = None, **kwargs: Any) -> ModelResponse:
        payload: dict[str, Any] = {"model": self.model, "prompt": prompt, "stream": False}
        if system:
            payload["system"] = system
        payload.update({k: v for k, v in kwargs.items() if k in ("options", "keep_alive", "images", "format")})
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                start = time.monotonic()
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(f"{self.base_url}/api/generate", json=payload)
                resp.raise_for_status()
                data = resp.json()
                return ModelResponse(
                    text=data.get("response", ""),
                    model=self.model,
                    backend=self.name,
                    duration_ms=int((time.monotonic() - start) * 1000),
                    raw=data,
                )
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(1)
        raise ModelUnavailableError(f"{self.name}: inference failed ({last_error})")


class ModelRouter:
    def __init__(
        self,
        local: InferenceBackend | None = None,
        colab: InferenceBackend | None = None,
        colab_approved: bool | None = None,
    ) -> None:
        self.local = local
        self.colab = colab
        self.colab_approved = (
            settings.hybrid_requires_explicit_approval
            if colab_approved is None
            else colab_approved
        )

    def route(self, strict_local: bool = False) -> InferenceBackend | None:
        """Pick a backend. None means 'no AI available' (graceful degradation)."""
        if not strict_local and self.colab and self.colab_approved and self.colab.available():
            return self.colab
        if self.local and self.local.available():
            return self.local
        return None

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        strict_local: bool = False,
        **kwargs: Any,
    ) -> ModelResponse:
        backend = self.route(strict_local=strict_local)
        if backend is None:
            raise ModelUnavailableError(
                "No AI backend available (local Ollama absent and Colab not connected/approved)"
            )
        return backend.generate(prompt, system=system, **kwargs)


def default_router() -> ModelRouter:
    """Router wired from settings. Colab backend only when a tunnel URL is set."""
    local: InferenceBackend | None = None
    if settings.ollama_url.startswith(("http://", "https://")):
        local = OllamaBackend(
            "local-ollama",
            settings.ollama_url,
            settings.ollama_reasoning_model,
            timeout=settings.ollama_timeout_seconds,
            retries=settings.ollama_retries,
        )
    colab: InferenceBackend | None = None
    if settings.colab_ollama_url:
        colab = OllamaBackend(
            "colab-ollama",
            settings.colab_ollama_url,
            settings.ollama_reasoning_model,
            timeout=settings.ollama_timeout_seconds,
            retries=settings.ollama_retries,
        )
    return ModelRouter(local=local, colab=colab)