"""Perceptual d-hash adapter (Phase 7)."""

from __future__ import annotations

import time

from tools.base import ToolAdapter, ToolFinding, ToolResult
from tools.photo.base import dhash_hex, hamming_distance


class PerceptualHashAdapter(ToolAdapter):
    name = "photo-phash"
    target_types = ("image",)

    def run(self, target: str) -> ToolResult:
        start = time.perf_counter()
        result = ToolResult(self.name)
        try:
            phash = dhash_hex(target)
        except (OSError, ValueError) as exc:
            result.status = "failed"
            result.errors.append(f"cannot hash image: {exc}")
            result.coverage = {"sources_total": 1, "sources_checked": 0,
                               "sources_failed": 1, "note": "unreadable file"}
            return result
        result.findings.append(ToolFinding(
            type="image_perceptual_hash",
            title="Perceptual image hash (d-hash)",
            source=self.name,
            evidence=f"phash={phash}\n(hamming distance used for matching)",
            confidence="confirmed",
            severity="informational",
        ))
        result.status = "completed"
        result.coverage = {"sources_total": 1, "sources_checked": 1,
                           "sources_failed": 0, "note": "local file"}
        result.duration_ms = int((time.perf_counter() - start) * 1000)
        return result


def phash_matches(a_hex: str, b_hex: str, threshold: int = 10) -> bool:
    dist = hamming_distance(a_hex, b_hex)
    return dist >= 0 and dist <= threshold