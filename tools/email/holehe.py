"""Holehe-style email account check (site-manifest driven, local-first)."""

from __future__ import annotations

from pathlib import Path

import httpx

from tools.sitecheck import SiteCheckAdapter, load_manifest

DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "site_manifests" / "email.json"


class HoleheAdapter(SiteCheckAdapter):
    """email → list of sites where the address may have an account."""

    def __init__(
        self,
        client: httpx.Client | None = None,
        manifest_path: Path | None = None,
        timeout: float = 10.0,
        manifest: list | None = None,
    ) -> None:
        sites = manifest if manifest is not None else (load_manifest(manifest_path or DEFAULT_MANIFEST) or [])
        super().__init__(tool="holehe", target_type="email", manifest=sites, client=client, timeout=timeout)