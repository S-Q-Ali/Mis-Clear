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

    colab_job_dispatcher_url: str = ""
    colab_approval_required: bool = True

    default_scan_mode: str = "local"
    hybrid_requires_explicit_approval: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()