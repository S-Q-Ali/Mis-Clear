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

    default_scan_mode: str = "local"
    hybrid_requires_explicit_approval: bool = True

    # OSINT tool adapters (Phase 6)
    osint_enabled: bool = True
    osint_timeout_seconds: float = 10.0
    osint_manifest_email: str = "tools/site_manifests/email.json"
    osint_manifest_username: str = "tools/site_manifests/username.json"

    # Photo forensics (Phase 7)
    upload_dir: str = "data/uploads"
    upload_max_bytes: int = 20 * 1024 * 1024  # 20 MB

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()