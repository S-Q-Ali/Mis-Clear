"""Slice 5: takedown — curated removal registry lookup + category-aware procedures.

Deterministic, no network:
  - removal.json records resolve registrable domains to official removal channels
  - category-aware procedure selection: exact domain record wins, else curated
    category template (adult/image → takedown template, data-broker → opt-out)
  - unknown domains stay honest (known=False, no invented URL)
"""

from app.backend.services.removal_registry import (
    find_removal_record,
    removal_channel_for,
    removal_url_for,
)
from app.backend.services.takedown_procedures import (
    CATEGORY_TEMPLATES,
    procedure_for_finding,
)


def test_find_removal_record_exact_domain():
    rec = find_removal_record("https://www.spokeo.com/person/x")
    assert rec is not None
    assert rec["domain"] == "spokeo.com"
    assert rec["category"] == "data-broker"
    assert rec["removal_url"].startswith("https://")
    assert rec["removal_channel"] == "anonymous_form"


def test_find_removal_record_subdomain_resolves():
    rec = find_removal_record("http://github.com/u/alice")
    assert rec["domain"] == "github.com"
    assert rec["removal_channel"] == "account_delete"


def test_find_removal_record_unknown_returns_none():
    assert find_removal_record("https://obscure-xyz.test/u/jane") is None


def test_find_removal_record_no_url_returns_none():
    assert find_removal_record(None) is None


def test_channel_helpers_honest_defaults():
    assert removal_channel_for("https://spokeo.com/x") == "anonymous_form"
    assert removal_channel_for("https://nope.test/x") == "manual"
    assert removal_url_for("https://spokeo.com/x") is not None
    assert removal_url_for("https://nope.test/x") is None


def test_category_templates_present():
    assert set(CATEGORY_TEMPLATES) >= {"data-broker", "adult", "forum", "social"}


def test_procedure_for_finding_uses_category_template_when_no_curated_record():
    # adult-domain finding without an exact removal record -> adult takedown template
    proc = procedure_for_finding("https://adult-example.test/topic/x", finding_type="image_nsfw")
    assert proc.known is False or proc.category == "adult"
    assert proc.steps and any("takedown" in s.lower() or "report" in s.lower() for s in proc.steps)


def test_procedure_for_finding_exact_record_wins():
    proc = procedure_for_finding("https://www.spokeo.com/person/x", finding_type="email_exposure")
    assert proc.known is True
    assert proc.organization
    assert proc.procedure_url == removal_url_for("https://www.spokeo.com/person/x")


def test_procedure_for_finding_data_broker_uses_optout_template():
    proc = procedure_for_finding("https://whitepages.com/person/x", finding_type="email_exposure")
    assert proc.category == "data-broker"
    assert any("opt" in s.lower() for s in proc.steps)


def test_procedure_for_finding_nsfw_uses_takedown_template():
    proc = procedure_for_finding("https://some-adult-site-xyz.test/g/1", finding_type="image_nsfw")
    assert proc.category == "adult"
    assert proc.known is False
    assert "without consent" in "\n".join(proc.steps).lower() or "consent" in "\n".join(proc.steps).lower()