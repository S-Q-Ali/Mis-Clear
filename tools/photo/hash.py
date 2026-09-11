"""md5 + sha256 file hash adapter (Phase 7)."""

from __future__ import annotations

import time

from tools.base import ToolAdapter, ToolFinding, ToolResult
from tools.photo.base import md5_hex, sha256_hex


class PhotoHashAdapter(ToolAdapter):
    name = "photo-hash"
    target_types = ("image",)

    def run(self, target: str) -> ToolResult:
        start = time.perf_counter()
        result = ToolResult(self.name)
        try:
            md5 = md5_hex(target)
            sha = sha256_hex(target)
        except (OSError, ValueError) as exc:
            result.status = "failed"
            result.errors.append(f"cannot read image: {exc}")
            result.coverage = {"sources_total": 1, "sources_checked": 0,
                               "sources_failed": 1, "note": "unreadable file"}
            return result
        result.findings.append(ToolFinding(
            type="image_hash",
            title="File integrity hashes",
            source=self.name,
            evidence=f"md5={md5}\nsha256={sha}",
            confidence="confirmed",
            severity="informational",
        ))
        result.status = "completed"
        result.coverage = {"sources_total": 1, "sources_checked": 1,
                           "sources_failed": 0, "note": "local file"}
        result.duration_ms = int((time.perf_counter() - start) * 1000)
        return result