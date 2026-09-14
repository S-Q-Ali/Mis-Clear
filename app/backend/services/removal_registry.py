"""Removal registry lookup (Phase 16, slice 5) — curated records, deterministic.

Reads `tools/site_manifests/removal.json` and resolves any URL/domain to its
official, stable removal/opt-out/takedown record. Resolution rules:

  - exact registrable-domain record wins;
  - subdomains fall through to their registrable base;
  - unknown domains are HONEST — None, never a guessed URL.

Drives category-aware procedure selection (takedown_procedures) and the
per-finding removal executor (slice 6). The executor re-reads this registry at
execution time so the stored instruction text and the executed channel can never
drift.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from app.backend.services.site_advisory import _hostname_of, _registrable

MANIFEST_DIR = Path(__file__).resolve().parent.parent.parent.parent / "tools" / "site_manifests"
REMOVAL_FILE = MANIFEST_DIR / "removal.json"


@lru_cache(maxsize=1)
def load_removals() -> dict[str, Any]:
    if not REMOVAL_FILE.exists():
        return {"removals": []}
    import json

    return json.loads(REMOVAL_FILE.read_text(encoding="utf-8"))


def _index() -> dict[str, dict[str, Any]]:
    return {r["domain"]: r for r in load_removals().get("removals", [])}


def _lookup(url_or_domain: str | None) -> dict[str, Any] | None:
    host = _hostname_of(url_or_domain)
    if not host:
        return None
    idx = _index()
    if host in idx:
        return idx[host]
    base = _registrable(host)
    return idx.get(base)


def find_removal_record(url_or_domain: str | None) -> dict[str, Any] | None:
    """Return a copy of the curated removal record for a URL/domain, else None."""
    rec = _lookup(url_or_domain)
    return dict(rec) if rec else None


def removal_channel_for(url_or_domain: str | None) -> str:
    """Channel: anonymous_form | email | account_delete | manual (default)."""
    rec = _lookup(url_or_domain)
    return rec.get("removal_channel", "manual") if rec else "manual"


def removal_url_for(url_or_domain: str | None) -> str | None:
    rec = _lookup(url_or_domain)
    return rec.get("removal_url") if rec else None


def removal_category_for(url_or_domain: str | None) -> str | None:
    rec = _lookup(url_or_domain)
    return rec.get("category") if rec else None