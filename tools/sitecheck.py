"""Site-manifest engine powering holehe (email) and sherlock (username) adapters.

A manifest is a JSON list of `SiteSpec`:
    {
      "name": str,                     // site label, used as finding.source
      "mode": "email" | "username",
      "method": "GET" | "POST",        // email: POST form check; username: GET profile
      "probe_url": str,                // may contain {target} placeholder
      "form_field": str | null,        // email-mode POST form field name
      "exists_marker": str | null,     // substring (regex) pathmatched in the body
      "missing_marker": str | null,    // substring (regex) proving absence
      "error_status_codes": [int],     // username-mode: statuses that mean 'absent'
      "category": str | null,          // curated taxonomy: social|forum|data-broker|adult|legit|...
      "removal_url": str | null,       // official removal/opt-out/takedown page (https, curated)
      "removal_channel": str | null    // how removal happens: anonymous_form|email|account_delete|manual
    }

Presence is reported as a `probable` finding (a third-party page implies the
account/address exists there, but the laptop is not the system of record for
that site). Reserved statuses: some sites mark blocked/missing distinctly.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import httpx

from app.backend.security.url_safety import formatted_url_matches, probe_url_safe
from tools.base import ToolAdapter, ToolFinding, ToolResult


class SiteSpec:
    def __init__(self, raw: dict[str, Any]) -> None:
        self.name = raw["name"]
        self.mode = raw.get("mode", "email")
        self.method = raw.get("method", "POST" if self.mode == "email" else "GET").upper()
        self.probe_url = raw["probe_url"]
        self.form_field = raw.get("form_field")
        self.exists_marker = raw.get("exists_marker")
        self.missing_marker = raw.get("missing_marker")
        self.error_status_codes = [int(c) for c in raw.get("error_status_codes", [])]
        self.category = raw.get("category")
        self.removal_url = raw.get("removal_url")
        self.removal_channel = raw.get("removal_channel")

    def __lt__(self, other: SiteSpec) -> bool:
        return (self.name or "").lower() < (other.name or "").lower()

    def exists(self, status_code: int, body: str) -> bool | None:
        """None = inconclusive. GET: 404-class statuses mean absent; when the
        site declares markers, ONLY a marker match may establish presence
        (everything else is inconclusive, never a plain 200 guess)."""
        if self.method == "GET":
            if status_code in self.error_status_codes:
                return False
            if self.exists_marker and re.search(self.exists_marker, body):
                return True
            if self.missing_marker and re.search(self.missing_marker, body):
                return False
            if self.exists_marker or self.missing_marker:
                return None
            return status_code == 200
        if self.missing_marker and re.search(self.missing_marker, body):
            return False
        if self.exists_marker and re.search(self.exists_marker, body):
            return True
        return None


def load_manifest(path: str | Path) -> list[SiteSpec] | None:
    p = Path(path)
    if not p.exists():
        return None
    with p.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return [SiteSpec(s) for s in data["sites"]]


class SiteCheckAdapter(ToolAdapter):
    """Checks a target against a site manifest (email or username mode)."""

    def __init__(
        self,
        tool: str,
        target_type: str,
        manifest: list[SiteSpec],
        client: httpx.Client | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.name = tool
        self.target_types = (target_type,)
        self.sites = manifest
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=True)
        self.timeout = timeout

    def run(self, target: str) -> ToolResult:
        start = time.monotonic()
        result = ToolResult(tool=self.name, status="blocked", coverage={})
        sources_total = len(self.sites)
        sources_checked = 0
        sources_failed = 0
        matched_url: str | None = None
        for spec in self.sites:
            unsafe = probe_url_safe(spec.probe_url)
            if unsafe:
                sources_failed += 1
                result.errors.append(f"{spec.name}: skipped unsafe probe URL ({unsafe})")
                continue
            url = spec.probe_url.format(target=target)
            if not formatted_url_matches(url, spec.probe_url):
                sources_failed += 1
                result.errors.append(f"{spec.name}: target would leave the manifest host — skipped")
                continue
            try:
                if spec.method == "POST":
                    body = {"target": target}
                    if spec.form_field:
                        body = {spec.form_field: target}
                    resp = self.client.post(url, data=body, timeout=self.timeout)
                else:
                    resp = self.client.get(url, timeout=self.timeout)
                resp.raise_for_status()
                exists = spec.exists(resp.status_code, resp.text)
                sources_checked += 1
                if exists is True:
                    result.findings.append(
                        ToolFinding(
                            type=f"{spec.mode}_account",
                            title=f"Account exists on {spec.name}",
                            source=spec.name,
                            url=url,
                            evidence=f"{spec.name} reports the {spec.mode} exists",
                            confidence="probable",
                            severity="medium",
                            scope="public-presence",
                        )
                    )
                    matched_url = url
                elif exists is None:
                    sources_failed += 1
                    result.errors.append(f"{spec.name}: inconclusive response")
            except httpx.HTTPError as exc:
                sources_failed += 1
                result.errors.append(f"{spec.name}: {exc}")
        result.coverage = {
            "sources_total": sources_total,
            "sources_checked": sources_checked,
            "sources_failed": sources_failed,
            "note": "site manifest probe",
        }
        result.status = "completed" if sources_checked > 0 or sources_failed > 0 else "blocked"
        result.duration_ms = int((time.monotonic() - start) * 1000)
        result.raw_reference = matched_url or (f"{self.name}: {sources_checked}/{sources_total} sites")
        if sources_total == 0:
            result.status = "blocked"
            result.coverage["note"] = "no sites configured"
        return result