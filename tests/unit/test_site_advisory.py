"""Slice 2: site-advisory — deterministic domain reputation from categories.json.

Pure, deterministic catalog lookup. No network. No AI. Unknown domain must be
honest (recommended=None), never guessed.
"""

from app.backend.services.site_advisory import (
    advisory_for,
    category_of,
    load_advisory,
)


def test_advisory_data_loads():
    data = load_advisory()
    assert data["categories"]
    assert data["domains"]


def test_known_domain_resolves_data_broker_not_recommended():
    adv = advisory_for("https://www.spokeo.com/person/alice/123")
    assert adv["category"] == "data-broker"
    assert adv["recommended"] is False
    assert adv["rationale"] and len(adv["rationale"]) > 10


def test_known_domain_via_subdomain_and_scheme():
    adv = advisory_for("http://www.reddit.com/r/privacy")
    assert adv["category"] == "forum"
    assert adv["recommended"] is True


def test_unknown_domain_is_honest_not_guessed():
    adv = advisory_for("https://obscure-xyz.test/u/jane")
    assert adv["recommended"] is None
    assert adv["category"] == "unknown"
    assert "unknown" in adv["rationale"].lower()


def test_no_url_returns_unknown_honest():
    adv = advisory_for(None)
    assert adv["recommended"] is None
    assert adv["category"] == "unknown"


def test_category_of_suffix_matching():
    # exact base key wins over suffix of similar key
    assert category_of("app.spokeo.com") == "data-broker"
    assert category_of("www.github.com") == "dev"
    # bare registrable domain
    assert category_of("github.com") == "dev"


def test_bad_url_does_not_raise():
    adv = advisory_for("not-a-url")
    assert adv["recommended"] is None