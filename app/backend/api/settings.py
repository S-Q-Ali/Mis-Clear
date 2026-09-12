"""Read-only settings surface for the UI — no write endpoint exists by design."""

from fastapi import APIRouter

from app.backend.api.workers import worker_status
from app.backend.config import settings
from app.backend.schemas import SettingsOut

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings() -> SettingsOut:
    ws = worker_status()
    return SettingsOut(
        readOnly=True,
        osintEnabled=settings.osint_enabled,
        defaultScanMode=settings.default_scan_mode,
        hybridRequiresExplicitApproval=settings.hybrid_requires_explicit_approval,
        localAiConfigured=ws.localAiConfigured,
        localAiAvailable=ws.localAiAvailable,
        colabAiConfigured=ws.colabAiConfigured,
        colabAiAvailable=ws.colabAiAvailable,
        colabDispatcherConfigured=ws.colabDispatcherConfigured,
        colabApprovalRequired=ws.colabApprovalRequired,
        uploadMaxBytes=settings.upload_max_bytes,
    )