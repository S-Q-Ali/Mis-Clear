"""Deterministic site advisory (Phase 16, slice 2) — curated ratings, never guessed.

Reads `tools/site_manifests/categories.json` once and resolves any URL/domain to
a category + recommended verdict. Rule set is purely deterministic:

  - exact registrable-domain key wins;
  - subdomains fall through to their registrable base;
  - unknown domains are HONEST: recommended=None, category=unknown. AI is never
    used here and no recommendation is ever invented.

Used at render/research time to badge each finding with a `recommended /
not-recommended` advisory and to steer takedown procedure choice.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

MANIFEST_DIR = Path(__file__).resolve().parent.parent.parent.parent / "tools" / "site_manifests"
CATEGORIES_FILE = MANIFEST_DIR / "categories.json"

UNKNOWN_RATIONALE = (
    "No curated rating is on file for this domain; treat it as unknown "
    "and verify the site's identity before trusting or engaging it."
)


def _hostname_of(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    for prefix in ("https://", "http://", "ftp://", "//"):
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    value = value.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if "@" in value:  # strip user part if an email slipped in
        value = value.rsplit("@", 1)[-1]
    host = value.lower().rstrip(".")
    if not host or " " in host or ":" in host:
        return None
    return host


def _registrable(hostname: str) -> str:
    parts = hostname.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return hostname


@lru_cache(maxsize=1)
def load_advisory() -> dict[str, Any]:
    """Load the curated category taxonomy (cached)."""
    if not CATEGORIES_FILE.exists():
        return {"categories": {}, "domains": {}}
    import json

    return json.loads(CATEGORIES_FILE.read_text(encoding="utf-8"))


def category_of(domain_or_url: str) -> str | None:
    """Resolve a domain/URL to its curated category, else None (unknown)."""
    data = load_advisory()
    domains = data.get("domains", {})
    host = _hostname_of(domain_or_url)
    if not host:
        return None
    if host in domains:
        return domains[host].get("category")
    base = _registrable(host)
    if base in domains:
        return domains[base].get("category")
    return None


def advisory_for(url: str | None) -> dict[str, Any]:
    """Deterministic advisory verdict for a finding URL (or its absence)."""
    data = load_advisory()
    domains = data.get("domains", {})
    host = _hostname_of(url)
    if not host:
        return {
            "category": "unknown",
            "recommended": None,
            "rationale": "No URL recorded for this finding.",
        }
    key = host if host in domains else (_registrable(host) if _registrable(host) in domains else None)
    if key is None:
        return {
            "category": "unknown",
            "recommended": None,
            "rationale": UNKNOWN_RATIONALE,
        }
    entry = domains[key]
    rationale = entry.get("rationale") or (
        f"Curated category: {entry.get('category')}."
    )
    return {
        "category": entry.get("category"),
        "recommended": entry.get("recommended"),
        "rationale": rationale,
    }