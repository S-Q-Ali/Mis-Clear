"""Slice 1: catalog-expand — SiteSpec metadata + curated category/removal manifests.

These are pure, deterministic catalog tests: no network, synthetic tensors only.
The catalogs are curated metadata (category taxonomy + official removal channels)
and must stay honest — every removal URL must be https and real; unknown
domains must classify as unknown (never guessed).
"""

import json
from pathlib import Path

from tools.sitecheck import SiteSpec, load_manifest

MANIFEST_DIR = Path(__file__).resolve().parent.parent.parent / "tools" / "site_manifests"


# ---------------- SiteSpec metadata ----------------

def test_sitespec_parses_optional_removal_metadata():
    spec = SiteSpec({
        "name": "n",
        "mode": "username",
        "probe_url": "https://x.test/{target}",
        "category": "data-broker",
        "removal_url": "https://x.test/optout",
        "removal_channel": "anonymous_form",
    })
    assert spec.category == "data-broker"
    assert spec.removal_url == "https://x.test/optout"
    assert spec.removal_channel == "anonymous_form"


def test_sitespec_defaults_when_metadata_absent():
    spec = SiteSpec({"name": "n", "probe_url": "https://x.test/{target}"})
    assert spec.category is None
    assert spec.removal_url is None
    assert spec.removal_channel is None


# ---------------- email catalog ----------------

def test_email_manifest_sites_carry_category_and_removal():
    specs = load_manifest(MANIFEST_DIR / "email.json")
    assert specs
    for s in specs:
        assert s.category, f"{s.name}: missing category"
        # optional removal metadata: when present it must be a real https URL
        if s.removal_url:
            assert s.removal_url.startswith("https://"), f"{s.name}: removal_url not https"
            assert s.removal_channel, f"{s.name}: removal_url without channel"


# ---------------- category taxonomy ----------------

def test_category_manifest_loads_and_stays_honest():
    data = json.loads((MANIFEST_DIR / "categories.json").read_text(encoding="utf-8"))
    domains = data["domains"]
    assert domains, "category manifest must have entries"
    categories = set(data["categories"])
    for domain, entry in domains.items():
        assert "@" not in domain and "://" not in domain, f"{domain}: domain keys only"
        assert entry["category"] in categories, f"{domain}: unknown category"
        rationale = entry.get("rationale")
        assert rationale and len(rationale) > 10, f"{domain}: missing honest rationale"


# ---------------- removal registry ----------------

def test_removal_registry_is_curated_and_https_only():
    data = json.loads((MANIFEST_DIR / "removal.json").read_text(encoding="utf-8"))
    entries = data["removals"]
    assert len(entries) >= 15, "removal registry must be a real curated catalog"
    seen = set()
    for e in entries:
        assert e["domain"], "domain required"
        assert e["domain"] not in seen, f"{e['domain']}: duplicate"
        seen.add(e["domain"])
        assert e["organization"], f"{e['domain']}: organization required"
        assert e["removal_url"].startswith("https://"), f"{e['domain']}: removal_url must be https"
        assert e["removal_channel"], f"{e['domain']}: removal_channel required"