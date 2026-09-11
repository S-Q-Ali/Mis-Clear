"""Adapter registry — maps target types to the default tool set (Phase 6).

Stays backend-agnostic: configuration is passed in, not imported from the app.
`client_factory` lets tests inject mock transports so no real network is used.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import httpx

from tools.base import ToolAdapter
from tools.email.holehe import HoleheAdapter
from tools.sitecheck import load_manifest
from tools.username.sherlock import SherlockAdapter
from tools.web.dns import DnsAdapter
from tools.web.github import GithubAdapter
from tools.web.search import SearchAdapter
from tools.web.whois import WhoisAdapter

MANIFEST_DIR = Path(__file__).resolve().parent / "site_manifests"

ClientFactory = Callable[[], httpx.Client | None]


def build_registry(
    *,
    manifest_email: str | Path | None = None,
    manifest_username: str | Path | None = None,
    timeout: float = 10.0,
    client_factory: ClientFactory | None = None,
) -> list[ToolAdapter]:
    """Default adapter set. Manifests default to the packaged samples
    (synthetic hosts — replace with real catalogs before user-facing scans)."""
    make = client_factory or (lambda: None)

    def client() -> httpx.Client | None:
        return make()

    adapters: list[ToolAdapter] = [
        DnsAdapter(client=client(), timeout=timeout),
        WhoisAdapter(client=client(), timeout=timeout),
        SearchAdapter(client=client(), timeout=timeout),
        GithubAdapter(client=client(), timeout=timeout),
    ]
    email_path = Path(manifest_email) if manifest_email else MANIFEST_DIR / "email.json"
    user_path = Path(manifest_username) if manifest_username else MANIFEST_DIR / "username.json"
    email_sites = load_manifest(email_path)
    if email_sites:
        adapters.append(HoleheAdapter(client=client(), manifest=email_sites, timeout=timeout))
    user_sites = load_manifest(user_path)
    if user_sites:
        adapters.append(SherlockAdapter(client=client(), manifest=user_sites, timeout=timeout))
    return adapters


def adapters_for(
    target_type: str,
    registry: list[ToolAdapter] | None = None,
    client_factory: ClientFactory | None = None,
) -> list[ToolAdapter]:
    reg = registry if registry is not None else build_registry(client_factory=client_factory)
    return [a for a in reg if target_type in a.target_types]