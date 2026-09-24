"""Agent brain: routes reasoning to an available backend (SPEC-agent-core).

Order (deterministic): approved Colab Ollama → local Ollama → unavailable.
The brain is optional by design: when no backend answers, the loop reports
`blocked` and the app never depends on AI.
"""

from __future__ import annotations

from app.backend.services.model_router import (
    ModelRouter,
    ModelUnavailableError,
    OllamaBackend,
    default_router,
)


class AgentBrain:
    def __init__(self, router: ModelRouter | None = None, model: str | None = None) -> None:
        self.router = router or default_router()
        self.model = model or ""

    def available(self) -> bool:
        return self.router.route(strict_local=False) is not None

    @property
    def backend_name(self) -> str:
        backend = self.router.route(strict_local=False)
        return getattr(backend, "name", "none") if backend else "none"

    def complete(self, system: str, prompt: str, timeout: int | None = None) -> str:
        backend = self.router.route(strict_local=False)
        if backend is None:
            raise ModelUnavailableError("no AI backend available for the agent")
        if self.model and self.model != getattr(backend, "model", None):
            backend = OllamaBackend(
                name=f"{getattr(backend, 'name', 'backend')}-agent",
                base_url=getattr(backend, "base_url", ""),
                model=self.model,
                timeout=timeout,
            )
        resp = backend.generate(system=system, prompt=prompt)
        return resp.text