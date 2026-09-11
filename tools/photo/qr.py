"""Local QR code decode adapter (Phase 7).

1D barcodes are deferred to the Colab vision worker (Phase 8). Decoded
payloads are untrusted data: reported, never executed.
"""

from __future__ import annotations

import time

import cv2

from tools.base import ToolAdapter, ToolFinding, ToolResult


class QrAdapter(ToolAdapter):
    name = "photo-qr"
    target_types = ("image",)

    def run(self, target: str) -> ToolResult:
        start = time.perf_counter()
        result = ToolResult(self.name)
        img = cv2.imread(target, cv2.IMREAD_GRAYSCALE)
        if img is None:
            result.status = "failed"
            result.errors.append("cannot read image via OpenCV")
            result.coverage = {"sources_total": 1, "sources_checked": 0,
                               "sources_failed": 1, "note": "unreadable file"}
            return result
        detector = cv2.QRCodeDetector()
        decoded, decoded_info, _, _ = detector.detectAndDecodeMulti(img)
        payloads: list[str] = []
        if decoded and decoded_info is not None:
            for text in decoded_info:
                if isinstance(text, str) and text.strip():
                    payloads.append(text)
        if not payloads:
            result.status = "completed"
            result.coverage = {"sources_total": 1, "sources_checked": 1,
                               "sources_failed": 0, "note": "no QR code found"}
            result.duration_ms = int((time.perf_counter() - start) * 1000)
            return result
        for text in payloads:
            result.findings.append(ToolFinding(
                type="image_qrcode",
                title="QR code decoded",
                source=self.name,
                evidence=text[:500],
                confidence="confirmed",
                severity="medium",
                scope="untrusted-payload",
            ))
        result.status = "completed"
        result.coverage = {"sources_total": 1, "sources_checked": 1,
                           "sources_failed": 0, "note": f"{len(payloads)} QR decoded"}
        result.duration_ms = int((time.perf_counter() - start) * 1000)
        return result