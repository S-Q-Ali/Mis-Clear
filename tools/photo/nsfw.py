"""Slice 4: NSFW/sensitive-content classifier adapter (Colab-first).

Privacy rules (Phase 16):
  - The image travels to the approved Colab worker as base64 via the existing
    vision transport; the laptop never calls a general-purpose public API.
  - Colab absent/unusable → status=blocked with the worker's errors copied.
    There is NO fabricated "benign" shortcut just to look safe.
  - A completed classification is surfaced verbatim from the model output and
    mapped into an `image_nsfw` finding with the raw JSON preserved as evidence.
"""

import json
import time
from pathlib import Path

from tools.base import ToolAdapter, ToolFinding, ToolResult

NSFW_SEVERITY_BY_CATEGORY = {
    "adult": "critical",
    "explicit": "critical",
    "nudity": "high",
    "violence": "high",
    "gore": "high",
    "benign": "informational",
}


def _severity(raw_text: str) -> str:
    """Deterministic severity from the model's category; benign → informational."""
    try:
        data = json.loads(raw_text)
        if not data.get("nsfw"):
            return "informational"
        cat = str(data.get("category", "adult")).lower()
        return NSFW_SEVERITY_BY_CATEGORY.get(cat, "high")
    except (ValueError, TypeError):
        return "medium"


class NsfwAdapter(ToolAdapter):
    name = "photo-nsfw"
    target_types = ("image",)

    def __init__(
        self,
        router=None,
        strict_local: bool = True,
        session_factory=None,
    ) -> None:
        self.router = router
        self.strict_local = strict_local
        self.session_factory = session_factory

    def _db_session(self):
        if self.session_factory is not None:
            return self.session_factory()
        from app.backend.database.engine import SessionLocal

        return SessionLocal()

    def run(self, target: str) -> ToolResult:
        import io

        from PIL import Image as PILImage

        from app.backend.services import vision_transport as vt

        start = time.perf_counter()
        result = ToolResult(self.name)
        if self.strict_local:
            result.status = "blocked"
            result.errors = [
                ("NSFW classification runs on the approved Colab worker; "
                 "use hybrid scan mode (explicit approval) to enable it")
            ]
            result.coverage = {"sources_total": 1, "sources_checked": 0,
                               "sources_failed": 1, "note": "local mode disables NSFW classification"}
            return result
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

        from app.backend.config import settings

        ttl = settings.colab_job_timeout_seconds
        db = self._db_session()
        try:
            job = vt.create_vision_job(
                db,
                job_type="nsfw_analysis",
                image_path=target,
                prompt=(
                    "You are a content-safety classifier. Classify the image with one JSON object"
                    ' {"nsfw": bool, "category": "benign"|"adult"|"nudity"|"explicit"|"violence"|"gore",'
                    ' "confidence": 0..1, "note": "short"} — nothing else.'
                ),
                model=settings.ollama_vision_model,
                capabilities=["vision"],
                ttl_seconds=ttl,
            )
            if vt.job_dispatcher.dispatcher_base_url():
                vt.submit_job_to_colab(db, job)
            job = vt.run_job_sync(db, job.job_id, timeout_seconds=ttl)
            if job is None:
                result.status = "blocked"
                result.errors = ["NSFW job record vanished"]
                result.coverage = {"sources_total": 1, "sources_checked": 0,
                                   "sources_failed": 1, "note": "job lost"}
                return result
            if job.status == "completed":
                r = job.result or {}
                text = (r.get("text") or "").strip()
                if r.get("ok") and text:
                    severity = _severity(text)
                    result.findings = [ToolFinding(
                        type="image_nsfw",
                        title="Sensitive-content classification of photo",
                        source=self.name,
                        evidence=text[:1000],
                        confidence="probable",
                        severity=severity,
                        scope="ai-analysis",
                    )]
                    result.status = "completed"
                    result.coverage = {
                        "sources_total": 1, "sources_checked": 1, "sources_failed": 0,
                        "note": f"colab worker (data_deleted={bool(job.data_deleted)})",
                    }
                    result.raw_reference = str(r.get("model") or "?")
                    result.duration_ms = int((time.perf_counter() - start) * 1000)
                    return result
            result.status = "blocked"
            result.errors = job.errors or [f"colab nsfw {job.status}"]
            result.coverage = {
                "sources_total": 1, "sources_checked": 0, "sources_failed": 1,
                "note": f"colab nsfw {job.status}; no fabricated verdict",
            }
            return result
        finally:
            db.close()