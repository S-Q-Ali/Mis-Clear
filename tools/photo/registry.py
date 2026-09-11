"""Photo forensics pipeline (Phase 7): ordered local-first adapter chain."""

from __future__ import annotations

from app.backend.services.model_router import ModelRouter
from tools.base import ToolAdapter
from tools.photo.exif import ExifAdapter
from tools.photo.hash import PhotoHashAdapter
from tools.photo.phash import PerceptualHashAdapter
from tools.photo.qr import QrAdapter
from tools.photo.vision import VisionAdapter


def photo_pipeline(router: ModelRouter | None = None, strict_local: bool = True) -> list[ToolAdapter]:
    return [
        PhotoHashAdapter(),
        PerceptualHashAdapter(),
        ExifAdapter(),
        QrAdapter(),
        VisionAdapter(router=router, strict_local=strict_local),
    ]