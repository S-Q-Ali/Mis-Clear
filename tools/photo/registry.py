"""Photo forensics pipeline (Phase 7 + Phase 16): ordered local-first adapter chain.

Phase 7: photo hashing, EXIF, QR, vision.
Phase 16: reverse image search (hybrid-only gate).
"""

from __future__ import annotations

from app.backend.services.model_router import ModelRouter
from tools.base import ToolAdapter
from tools.photo.exif import ExifAdapter
from tools.photo.hash import PhotoHashAdapter
from tools.photo.phash import PerceptualHashAdapter
from tools.photo.qr import QrAdapter
from tools.photo.reverse_search import ReverseImageSearchAdapter
from tools.photo.vision import VisionAdapter


def photo_pipeline(
    router: ModelRouter | None = None,
    strict_local: bool = True,
) -> list[ToolAdapter]:
    adapters: list[ToolAdapter] = [
        PhotoHashAdapter(),
        PerceptualHashAdapter(),
        ExifAdapter(),
        QrAdapter(),
        VisionAdapter(router=router, strict_local=strict_local),
    ]
    if not strict_local:
        adapters.append(ReverseImageSearchAdapter(allowed=True))
    return adapters