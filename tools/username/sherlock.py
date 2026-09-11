"""Sherlock-style username profile check (site-manifest driven, local-first)."""

from __future__ import annotations

from pathlib import Path

import httpx

from tools.sitecheck import SiteCheckAdapter, load_manifest

DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "site_manifests" / "username.json"


class SherlockAdapter(SiteCheckAdapter):
    """username → profiles the handle likely has across manifest sites."""

    def __init__(
        self,
        client: httpx.Client | None = None,
        manifest_path: Path | None = None,
        timeout: float = 10.0,
        manifest: list | None = None,
    ) -> None:
        sites = manifest if manifest is not None else (load_manifest(manifest_path or DEFAULT_MANIFEST) or [])
        super().__init__(
            tool="sherlock", target_type="username", manifest=sites, client=client, timeout=timeout
        )