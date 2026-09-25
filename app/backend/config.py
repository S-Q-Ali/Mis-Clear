"""Backend configuration via pydantic-settings (reads .env)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PG_", env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8000
    database_path: str = "data/database/privacy_guardian.db"
    log_level: str = "INFO"
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"

    ollama_url: str = "http://127.0.0.1:11434"
    ollama_reasoning_model: str = "qwen3:8b"
    ollama_vision_model: str = "gemma3:4b"
    ollama_timeout_seconds: int = 120
    ollama_retries: int = 2

    # Colab worker (optional; treated as temporary compute runtime)
    colab_job_dispatcher_url: str = ""
    # Ollama served on a Colab/site tunnel (optional AI worker), e.g. https://xxx.loca.lt
    colab_ollama_url: str = ""
    colab_approval_required: bool = True
    colab_request_timeout_seconds: int = 15
    # How long a photo vision/OCR job waits for a Colab worker before the
    # scan treats it as interrupted (no fabricated results).
    colab_job_timeout_seconds: int = 60

    default_scan_mode: str = "local"
    hybrid_requires_explicit_approval: bool = True

    # Agentic self-data investigator (SPEC-agent-*)
    agent_enabled: bool = True
    agent_max_steps: int = 20
    # Per-step brain budget. Tuned for a remote 27B brain on Colab (Q4_K_M@T4
    # cold-load + generation can exceed 30-90s per step); raise via
    # PG_AGENT_STEP_TIMEOUT_SECONDS for very slow GPUs.
    agent_step_timeout_seconds: float = 120.0
    # Optional model override for the agent brain; empty = router's reasoning model.
    agent_model: str = ""
    # Requests/minute per client for /api/agent/chat (S7 hardening).
    agent_rate_limit_per_minute: int = 20
    # k-anonymity breach range API (e.g. https://api.pwnedpasswords.com/range).
    # Empty = breach_check reports "not configured" (SPEC-self-data).
    breach_api_url: str = ""

    # OSINT tool adapters (Phase 6)
    osint_enabled: bool = True
    osint_timeout_seconds: float = 10.0
    osint_manifest_email: str = "tools/site_manifests/email.json"
    osint_manifest_username: str = "tools/site_manifests/username.json"

    # Photo forensics (Phase 7)
    upload_dir: str = "data/uploads"
    upload_max_bytes: int = 20 * 1024 * 1024  # 20 MB
    # Decompression-bomb guard (Phase 13): declared pixel count ceiling.
    upload_max_pixels: int = 50_000_000  # 50 MP

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def effective_default_scan_mode(self) -> str:
        """Hybrid (Colab-first) once any Colab compute endpoint is configured.

        Docs (COLAB_GPU_ARCHITECTURE): heavy AI work routes to the approved
        Colab worker when available; local Ollama is the graceful fallback.
        Sensitive data still requires explicit approval (scan_mode=hybrid).
        """
        if self.colab_ollama_url or self.colab_job_dispatcher_url:
            return "hybrid"
        return self.default_scan_mode


settings = Settings()