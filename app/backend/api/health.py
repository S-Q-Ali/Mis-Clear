"""Health endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "privacy-guardian",
        "time": datetime.now(timezone.utc).isoformat(),
    }