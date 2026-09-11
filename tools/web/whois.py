"""WHOIS-lite via RDAP (JSON over HTTPS). Modern, structured, no extra deps;
RDAP bootstrap resolves the authoritative server. Response JSON is untrusted."""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from tools.base import ToolAdapter, ToolFinding, ToolResult

RDAP_BOOTSTRAP = "https://rdap.org/domain/{domain}"


def _domain_of(target: str) -> str:
    target = (target or "").strip()
    if "://" in target:
        target = urlparse(target).netloc or target
    target = target.rstrip("/")
    if "." not in target or " " in target:
        raise ValueError(f"not a domain: {target!r}")
    return target


def _when(dates: list[Any], key: str) -> str | None:
    for item in dates or []:
        if item.get("eventAction") == key:
            return str(item.get("eventDate", ""))
    return None


class WhoisAdapter(ToolAdapter):
    name = "whois"
    target_types = ("custom", "domain")

    def __init__(self, client: httpx.Client | None = None, timeout: float = 10.0) -> None:
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=True)
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
        url = RDAP_BOOTSTRAP.format(domain=domain)
        try:
            resp = self.client.get(url, timeout=self.timeout)
        except httpx.HTTPError as exc:
            result.status = "failed"
            result.errors = [str(exc)]
            result.coverage = {"sources_total": 1, "sources_checked": 0, "sources_failed": 1}
            result.duration_ms = int((time.monotonic() - start) * 1000)
            return result

        if resp.status_code == 404:
            result.status = "completed"
            result.coverage = {
                "sources_total": 1,
                "sources_checked": 1,
                "sources_failed": 0,
                "note": "domain not found in RDAP",
            }
            result.duration_ms = int((time.monotonic() - start) * 1000)
            return result
        try:
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            result.status = "failed"
            result.errors = [str(exc)]
            result.coverage = {"sources_total": 1, "sources_checked": 0, "sources_failed": 1}
            result.duration_ms = int((time.monotonic() - start) * 1000)
            return result

        registrant = "unknown"
        for entity in data.get("entities", []):
            if "registrant" in (entity.get("roles") or []):
                vcard = entity.get("vcardArray", [[], []])
                for item in vcard[1] if len(vcard) > 1 else []:
                    if item and len(item) > 3 and item[0] == "fn":
                        registrant = str(item[3])
        registrant = registrant or "unknown"
        events = _when(data.get("events", []), "registration")
        updated = _when(data.get("events", []), "last changed")
        summary = {"domain": domain, "handle": data.get("handle"), "registration": events, "updated": updated,
                   "registrant": registrant}
        result.findings.append(
            ToolFinding(
                type="domain_registration",
                title=f"Domain {domain} is registered",
                source="rdap",
                url=url,
                evidence=json.dumps(summary, ensure_ascii=False)[:1000],
                confidence="confirmed",
                severity="informational",
                scope="public-registrar",
            )
        )
        result.status = "completed"
        result.coverage = {"sources_total": 1, "sources_checked": 1, "sources_failed": 0}
        result.raw_reference = url
        result.duration_ms = int((time.monotonic() - start) * 1000)
        return result