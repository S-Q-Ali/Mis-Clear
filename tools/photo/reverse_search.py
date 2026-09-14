"""Reverse image search adapter (Phase 16, slice 3) — Yandex Images HTML.

Routing (deterministic, privacy-gated):
  - `allowed=False` (scan_mode=local): blocked, no network call. Reverse search
    sends the image to a third-party engine, so it is ONLY available in
    hybrid/approved scans (explicit human approval).
  - `allowed=True` (scan_mode=hybrid): the image file is POSTed as multipart to
    the Yandex Images upload endpoint; candidate page links are extracted.

Response bodies are untrusted. Only link/JSON extraction happens — nothing is
executed or followed. Reverse-search hits are `weak` evidence: a similar image
appearing in an index is a lead, never proof of identity.

Provider seam: `provider` selects the engine ('yandex' default). Overriding
`parse_html_urls`/`parse_json_urls` via subclass allows adding Google Lens,
TinEye, or Bing Visual without touching this class.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import httpx

from tools.base import ToolAdapter, ToolFinding, ToolResult

YANDEX_UPLOAD_URL = "https://yandex.com/images-search"
_LINK_RE = re.compile(r'href="(https?://[^"]+)"')
_SERP_ITEM_RE = re.compile(r'<a[^>]+class="[^"]*serp-item__link[^"]*"[^>]+href="([^"]+)"', re.IGNORECASE)


class ReverseImageSearchAdapter(ToolAdapter):
    name = "photo-reverse-search"
    target_types = ("image",)

    def __init__(
        self,
        client: httpx.Client | None = None,
        provider: str = "yandex",
        allowed: bool = False,
        timeout: float = 20.0,
        max_results: int = 8,
    ) -> None:
        self.provider = provider
        self.allowed = allowed
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=True)
        self.timeout = timeout
        self.max_results = max_results

    def _blocked(self, result: ToolResult, note: str) -> ToolResult:
        result.status = "blocked"
        result.coverage = {
            "sources_total": 1,
            "sources_checked": 0,
            "sources_failed": 1,
            "note": note,
        }
        result.errors = [note]
        return result

    def _finding(self, url: str, evidence: str) -> ToolFinding:
        return ToolFinding(
            type="image_exposure",
            title=f"Visually similar image found online: {url}",
            source=self.provider,
            url=url,
            evidence=evidence[:500],
            confidence="weak",
            severity="medium",
            scope="public-index",
        )

    def parse_html_urls(self, html: str) -> list[str]:
        """Extract candidate image-page URLs from a search-results HTML body."""
        urls: list[str] = []
        for m in _SERP_ITEM_RE.finditer(html):
            urls.append(m.group(1))
        if not urls:
            for m in _LINK_RE.finditer(html):
                href = m.group(1)
                if any(ext in href.lower() for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif")):
                    urls.append(href)
        seen: set[str] = set()
        out: list[str] = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                out.append(u)
        return out[: self.max_results]

    def parse_json_urls(self, data: dict) -> list[str]:
        """Extract candidate URLs from a structured provider payload."""
        urls: list[str] = []
        for m in data.get("matches", []):
            u = m.get("url")
            if u:
                urls.append(u)
        return urls[: self.max_results]

    def run(self, target: str) -> ToolResult:
        start = time.monotonic()
        result = ToolResult(tool=self.name)
        if not self.allowed:
            return self._blocked(
                result,
                "reverse image search sends the image to a third-party engine; "
                "run this scan in hybrid (approved) mode to enable it",
            )
        image_path = Path(target)
        if not image_path.is_file():
            result.status = "failed"
            result.errors = [f"cannot read image: {target}"]
            result.coverage = {"sources_total": 1, "sources_checked": 0,
                               "sources_failed": 1, "note": "unreadable file"}
            result.duration_ms = int((time.monotonic() - start) * 1000)
            return result
        try:
            data = image_path.read_bytes()
            resp = self.client.post(
                YANDEX_UPLOAD_URL,
                files={"files[content]": ("image", data, "image/png")},
                params={"cbird": "2", "rpt": "imageview"},
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            result.status = "failed"
            result.errors = [str(exc)]
            result.coverage = {"sources_total": 1, "sources_checked": 0,
                               "sources_failed": 1, "note": f"{self.provider} error"}
            result.duration_ms = int((time.monotonic() - start) * 1000)
            return result

        try:
            js = resp.json()
            urls = self.parse_json_urls(js)
        except ValueError:
            urls = self.parse_html_urls(resp.text)

        for u in urls:
            result.findings.append(self._finding(u, f"{self.provider} similar-image index hit"))
        result.status = "completed"
        result.coverage = {
            "sources_total": 1,
            "sources_checked": 1,
            "sources_failed": 0,
            "note": f"{len(urls)} candidate page links parsed",
        }
        result.raw_reference = self.provider
        result.duration_ms = int((time.monotonic() - start) * 1000)
        return result