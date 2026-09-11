"""DNS-over-HTTPS adapter. No local resolver access required; output is
parsed as untrusted JSON. Substring/URL extraction only — never executes
content found in responses."""

from __future__ import annotations

import re
import time
from urllib.parse import urlparse

import httpx

from tools.base import ToolAdapter, ToolFinding, ToolResult

DOH_ENDPOINTS = ("https://cloudflare-dns.com/dns-query", "https://dns.google/resolve")
QUERY_TYPES = ("A", "AAAA", "NS", "MX", "TXT")


def _domain_of(target: str) -> str:
    target = (target or "").strip()
    if "://" in target:
        target = urlparse(target).netloc or target
    target = target.rstrip("/").split("@")[-1]
    if re.fullmatch(r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}", target):
        return target
    raise ValueError(f"not a domain: {target!r}")


class DnsAdapter(ToolAdapter):
    name = "dns"
    target_types = ("custom", "domain")

    def __init__(
        self,
        client: httpx.Client | None = None,
        endpoints: tuple[str, ...] = DOH_ENDPOINTS,
        timeout: float = 10.0,
    ) -> None:
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=True)
        self.endpoints = endpoints
        self.timeout = timeout

    def run(self, target: str) -> ToolResult:
        start = time.monotonic()
        result = ToolResult(tool=self.name, status="blocked")
        try:
            domain = _domain_of(target)
        except ValueError as exc:
            result.status = "failed"
            result.errors = [str(exc)]
            result.duration_ms = int((time.monotonic() - start) * 1000)
            return result

        records: dict[str, list[str]] = {}
        errors: list[str] = []
        queried: set[str] = set()
        for qtype in QUERY_TYPES:
            for ep in self.endpoints:
                try:
                    resp = self.client.get(
                        ep,
                        params={"name": domain, "type": qtype},
                        headers={"accept": "application/dns-json"},
                        timeout=self.timeout,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    answers = [a.get("data", "") for a in data.get("Answer", [])]
                    answers = [a for a in answers if a]
                    queried.add(qtype)
                    if answers:
                        records[qtype] = answers
                    break  # success: don't hit the fallback for this type
                except (httpx.HTTPError, ValueError) as exc:  # noqa: PERF203 - bounded fallback
                    errors.append(f"{qtype}@{ep.split('/')[2]}: {exc}")

        result.coverage = {
            "sources_total": len(QUERY_TYPES),
            "sources_checked": len(queried),
            "sources_failed": len(QUERY_TYPES) - len(queried),
            "note": "records returned mean the domain resolves (informational)",
        }
        result.duration_ms = int((time.monotonic() - start) * 1000)
        result.raw_reference = self.endpoints[0]
        if records:
            summary = "; ".join(f"{q}: {','.join(v)}" for q, v in records.items() if v)
            result.findings.append(
                ToolFinding(
                    type="domain_resolution",
                    title=f"Domain {domain} resolves",
                    source="dns-over-https",
                    url=f"{self.endpoints[0]}?name={domain}",
                    evidence=summary[:1000],
                    confidence="confirmed",
                    severity="informational",
                    scope="public-dns",
                )
            )
            result.status = "completed"
        elif queried:
            result.status = "completed"
            result.coverage["note"] = "domain does not resolve (no records)"
        else:
            result.status = "failed"
            result.errors = errors
        return result