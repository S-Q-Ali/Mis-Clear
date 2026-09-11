"""Local vision / OCR adapter (Phase 7, availability-aware).

Routing: local vision and heavy OCR run on the approved Colab AI worker
(Phase 8 job transport). Until that transport exists no vision finding is
ever fabricated: if no AI backend is available the adapter reports
status=blocked with an honest coverage note and the pipeline continues.

barcodes (1D) → vision worker; QR is decoded locally (photo-qr).
"""

from __future__ import annotations

import time

from app.backend.services.model_router import ModelRouter, ModelUnavailableError, default_router
from tools.base import ToolAdapter, ToolResult


class VisionAdapter(ToolAdapter):
    name = "photo-vision"
    target_types = ("image",)

    def __init__(self, router: ModelRouter | None = None, strict_local: bool = True) -> None:
        self.router = router if router is not None else default_router()
        self.strict_local = strict_local

    def run(self, target: str) -> ToolResult:
        start = time.perf_counter()
        result = ToolResult(self.name)
        try:
            backend = self.router.route(strict_local=self.strict_local)
        except Exception as exc:  # noqa: BLE001 - router must never crash the pipeline
            backend = None
            result.errors.append(f"router error: {exc}")
        if backend is None:
            result.status = "blocked"
            result.coverage = {
                "sources_total": 1,
                "sources_checked": 0,
                "sources_failed": 1,
                "note": "no AI backend for vision analysis (Colab worker not ready; Phase 8)",
            }
            result.duration_ms = int((time.perf_counter() - start) * 1000)
            return result
        result.status = "blocked"
        result.coverage = {
            "sources_total": 1,
            "sources_checked": 0,
            "sources_failed": 1,
            "note": "vision transport pending Phase 8 Colab worker (no fabricated results)",
        }
        result.errors.append(ModelUnavailableError.__name__)
        result.duration_ms = int((time.perf_counter() - start) * 1000)
        return result