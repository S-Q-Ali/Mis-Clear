"""Worker/backend status — honest, deterministic, no hidden cloud."""

from fastapi import APIRouter

from app.backend.config import settings
from app.backend.schemas import WorkerStatusOut
from app.backend.services.model_router import OllamaBackend

router = APIRouter(prefix="/api/workers", tags=["workers"])


def _probe_ollama(base_url: str) -> bool:
    if not base_url:
        return False
    return OllamaBackend("probe", base_url, settings.ollama_reasoning_model).available()


@router.get("")
def worker_status() -> WorkerStatusOut:
    colab_ai_configured = bool(settings.colab_ollama_url)
    colab_ai_available = colab_ai_configured and _probe_ollama(settings.colab_ollama_url)
    local_ai_configured = settings.ollama_url.startswith(("http://", "https://"))
    local_ai_available = local_ai_configured and _probe_ollama(settings.ollama_url)
    mode = "hybrid" if colab_ai_configured else "local_only"
    return WorkerStatusOut(
        mode=mode,
        localAiConfigured=local_ai_configured,
        localAiAvailable=local_ai_available,
        colabAiConfigured=colab_ai_configured,
        colabAiAvailable=colab_ai_available,
        colabDispatcherConfigured=bool(settings.colab_job_dispatcher_url),
        colabApprovalRequired=settings.colab_approval_required,
    )