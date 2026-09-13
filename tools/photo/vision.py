"""Local vision / OCR adapter (Phase 7 + Phase 15 transport wiring).

Routing (deterministic, never fabricated):
  - strict_local (scan_mode=local): local Ollama vision backend only. If no
    backend is available the adapter reports status=blocked honestly.
  - hybrid (scan_mode=hybrid): the image (base64) is sent as a Job to the
    approved Colab worker; the laptop waits for a terminal state and turns a
    completed result into an `image_vision` finding. Timeout/failure →
    status=blocked with the worker's errors copied.

barcodes/QR: QR is decoded locally (photo-qr); 1D barcodes stay on the worker
until a dedicated decoder is wired (never faked here).
"""

from __future__ import annotations

import base64
import io
import time
from pathlib import Path

from PIL import Image as PILImage

from app.backend.config import settings
from app.backend.services import vision_transport as vt
from app.backend.services.model_router import ModelRouter, ModelUnavailableError, default_router
from tools.base import ToolAdapter, ToolFinding, ToolResult

_VISION_PROMPT = (
    "You are an offline sighted analyst. Describe only what is objectively "
    "visible in this photo: scene, objects, people (no identities), printed or "
    "handwritten text you can read verbatim, signs, devices, and timestamps. "
    "State plainly when something is NOT visible. Never invent details."
)


class VisionAdapter(ToolAdapter):
    name = "photo-vision"
    target_types = ("image",)

    def __init__(
        self,
        router: ModelRouter | None = None,
        strict_local: bool = True,
        session_factory: callable | None = None,
    ) -> None:
        self.router = router if router is not None else default_router()
        self.strict_local = strict_local
        self.session_factory = session_factory

    def _db_session(self):
        """Session factory resolved at call time (picks up test/run-time swaps)."""
        if self.session_factory is not None:
            return self.session_factory()
        from app.backend.database.engine import SessionLocal

        return SessionLocal()

    def _finding(self, text: str) -> list:
        return [ToolFinding(
            type="image_vision",
            title="AI vision analysis of photo",
            source=self.name,
            evidence=text[:2000],
            confidence="probable",
            severity="medium",
            scope="ai-analysis",
        )]

    def _result_blocked(self, result: ToolResult, note: str, errors: list[str] | None = None) -> ToolResult:
        result.status = "blocked"
        result.coverage = {
            "sources_total": 1,
            "sources_checked": 0,
            "sources_failed": 1,
            "note": note,
        }
        if errors:
            result.errors = list(errors)
        return result

    def run(self, target: str) -> ToolResult:
        start = time.perf_counter()
        result = ToolResult(self.name)
        try:
            image_bytes = Path(target).read_bytes()
            with PILImage.open(io.BytesIO(image_bytes)) as probe:
                probe.verify()
        except OSError as exc:
            result.status = "failed"
            result.errors = [f"cannot read image: {exc}"]
            result.coverage = {"sources_total": 1, "sources_checked": 0,
                               "sources_failed": 1, "note": "unreadable file"}
            result.duration_ms = int((time.perf_counter() - start) * 1000)
            return result
        image_b64 = base64.b64encode(image_bytes).decode("ascii")

        if self.strict_local:
            self._run_local(result, image_b64, start)
        else:
            self._run_hybrid(result, target, start)
        return result

    def _run_local(self, result: ToolResult, image_b64: str, start: float) -> None:
        try:
            backend = self.router.route(strict_local=True)
        except Exception as exc:  # noqa: BLE001 - router must never crash the pipeline
            self._result_blocked(result, f"router error: {exc}", [str(exc)])
            return
        if backend is None:
            self._result_blocked(
                result,
                "no local AI vision backend available; use hybrid scan mode with an approved Colab worker",
            )
            return
        try:
            resp = backend.generate(_VISION_PROMPT, images=[image_b64])
        except ModelUnavailableError as exc:
            self._result_blocked(result, "local vision inference failed", [str(exc)])
            return
        text = (resp.text or "").strip()
        if not text:
            self._result_blocked(result, "local vision model returned empty output")
            return
        result.findings = self._finding(text)
        result.status = "completed"
        result.coverage = {
            "sources_total": 1,
            "sources_checked": 1,
            "sources_failed": 0,
            "note": f"local vision ({resp.backend} / {resp.model})",
        }
        result.raw_reference = f"{resp.backend}:{resp.model}"
        result.duration_ms = int((time.perf_counter() - start) * 1000) + resp.duration_ms

    def _run_hybrid(self, result: ToolResult, target: str, start: float) -> None:
        ttl = settings.colab_job_timeout_seconds
        db = self._db_session()
        try:
            job = vt.create_vision_job(
                db,
                job_type="vision_analysis",
                image_path=target,
                prompt=_VISION_PROMPT,
                model=settings.ollama_vision_model,
                capabilities=["vision"],
                ttl_seconds=ttl,
            )
            if vt.job_dispatcher.dispatcher_base_url():
                vt.submit_job_to_colab(db, job)
            job = vt.run_job_sync(db, job.job_id, timeout_seconds=ttl)
            if job is None:
                self._result_blocked(result, "vision job record vanished", ["job not found after submit"])
                return
            if job.status == "completed":
                r = job.result or {}
                text = (r.get("text") or "").strip()
                if r.get("ok") and text:
                    result.findings = self._finding(text)
                    result.status = "completed"
                    result.coverage = {
                        "sources_total": 1,
                        "sources_checked": 1,
                        "sources_failed": 0,
                        "note": f"colab worker (data_deleted={bool(job.data_deleted)})",
                    }
                    result.raw_reference = str(r.get("model") or "?")
                    result.duration_ms = int((time.perf_counter() - start) * 1000)
                    return
                self._result_blocked(result, "colab worker completed without usable output", job.errors or [])
                return
            self._result_blocked(
                result,
                f"colab vision {job.status} after {ttl}s wait",
                job.errors or [f"job {job.status}"],
            )
        finally:
            db.close()