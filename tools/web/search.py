"""Public web search adapter (DuckDuckGo HTML by default).

Only link + snippet extraction from the HTML payload. Search engines return
third-party indexes, so hits are `weak` evidence — never treated as confirmed.
Response bodies are untrusted; nothing is executed or followed beyond the
link extraction step."""

from __future__ import annotations

import re
import time
import urllib.parse

import httpx

from tools.base import ToolAdapter, ToolFinding, ToolResult

DDG_ENDPOINT = "https://html.duckduckgo.com/html/"
_LINK_RE = re.compile(r'class="result__url"[^>]*href="([^"]+)"')
_SNIPPET_RE = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>', re.DOTALL)


class SearchAdapter(ToolAdapter):
    name = "search"
    target_types = ("email", "username", "custom", "domain")

    def __init__(
        self,
        client: httpx.Client | None = None,
        endpoint: str = DDG_ENDPOINT,
        timeout: float = 10.0,
        max_results: int = 10,
    ) -> None:
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=True)
        self.endpoint = endpoint
        self.timeout = timeout
        self.max_results = max_results

    def run(self, target: str) -> ToolResult:
        start = time.monotonic()
        result = ToolResult(tool=self.name, status="completed")
        url = f"{self.endpoint}?q={urllib.parse.quote(target)}"
        try:
            resp = self.client.get(self.endpoint, params={"q": target}, timeout=self.timeout)
            resp.raise_for_status()
            html = resp.text
        except httpx.HTTPError as exc:
            result.status = "failed"
            result.errors = [str(exc)]
            result.coverage = {"sources_total": 1, "sources_checked": 0, "sources_failed": 1}
            result.duration_ms = int((time.monotonic() - start) * 1000)
            return result

        links = _LINK_RE.findall(html)[: self.max_results]
        snippets = [s.replace("&amp;", "&").replace("<b>", "").replace("</b>", "")
                    for s in _SNIPPET_RE.findall(html)[: self.max_results]]
        for i, link in enumerate(links):
            snippet = snippets[i] if i < len(snippets) else ""
            result.findings.append(
                ToolFinding(
                    type="search_hit",
                    title=f"Search engine hit: {link}",
                    source="duckduckgo",
                    url=link,
                    evidence=snippet[:300] or None,
                    confidence="weak",
                    severity="informational",
                    scope="public-index",
                )
            )
        result.coverage = {
            "sources_total": 1,
            "sources_checked": 1 if html else 0,
            "sources_failed": 0 if html else 1,
            "note": f"{len(links)} result links parsed",
        }
        result.raw_reference = url
        result.duration_ms = int((time.monotonic() - start) * 1000)
        return result