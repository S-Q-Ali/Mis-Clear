"""Unit tests for the deterministic risk engine (Phase 10, master plan §10)."""

import pytest

from app.backend.schemas import RiskBreakdownOut
from app.backend.services.risk_engine import (
    DEFAULT_WEIGHTS,
    correlation_factor,
    explain_risk,
    exposure_age_factor,
    level_for,
    score_finding,
    sensitivity_factor,
    severity_factor,
    source_reliability,
    validate_weights,
)


def test_weights_sum_to_one_per_defaults():
    assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(1.0)


def test_validate_weights_merges_defaults_and_rescales():
    w = validate_weights({"severity": 0.5, "confidence": 0.0})
    assert w["severity"] > DEFAULT_WEIGHTS["severity"]
    assert sum(w.values()) == pytest.approx(1.0)


def test_validate_weights_rejects_unknown_keys():
    with pytest.raises(ValueError):
        validate_weights({"bogus": 0.5})


def test_validate_weights_normalizes_partial_override():
    w = validate_weights({"severity": 0.9})
    assert sum(w.values()) == pytest.approx(1.0)
    assert w["severity"] > 0.5


def test_severity_normalization_ranks_ordered():
    assert severity_factor("informational") < severity_factor("low")
    assert severity_factor("low") < severity_factor("medium")
    assert severity_factor("medium") < severity_factor("high")
    assert severity_factor("high") < severity_factor("critical")
    assert severity_factor("critical") == 1.0
    assert severity_factor("") == severity_factor("low")


def test_source_reliability_known_and_unknown():
    assert source_reliability("rdap") == 0.8
    assert source_reliability("github.com") == 0.8
    assert source_reliability("Some_StrangE-Source!") >= 0.5
    assert source_reliability(None) == 0.5
    assert source_reliability("") == 0.5


def test_sensitivity_map():
    assert sensitivity_factor("image_gps") == 0.9
    assert sensitivity_factor("email_exposure") == 0.7
    assert sensitivity_factor("totally_new_type") == 0.5
    assert sensitivity_factor(None) == 0.5


def test_exposure_age_unknown_is_neutral_low_age_neutral():
    assert exposure_age_factor(None) == 1.0
    assert exposure_age_factor(0) == 1.0
    assert exposure_age_factor(1) == 1.0


def test_exposure_age_linear_decay_to_floor():
    assert exposure_age_factor(100) > exposure_age_factor(200)
    assert exposure_age_factor(1000) == 0.2
    assert exposure_age_factor(999999) == 0.2


def test_correlation_cap_at_three_peers():
    assert correlation_factor(0) == 0.0
    assert correlation_factor(1) > correlation_factor(0)
    assert correlation_factor(3) == 1.0
    assert correlation_factor(10) == 1.0
    assert correlation_factor(-5) == 0.0


def test_false_positive_gate_zeroes_score_everything():
    br = score_finding(
        severity="critical",
        confidence="false_positive",
        source="dns",
        finding_type="image_gps",
        related_peers=5,
    )
    assert br.gated is True
    assert br.score == 0.0
    assert br.riskScore == 0
    assert br.level == "negligible"
    # other factors still reported for transparency
    assert br.severity == 1.0
    assert br.confidence == 0.0


def test_higher_inputs_never_produce_lower_score():
    base = score_finding(
        severity="medium",
        confidence="possible",
        source="somewhere",
        finding_type="email_exposure",
    )
    boosted = score_finding(
        severity="critical",
        confidence="confirmed",
        source="rdap",
        finding_type="image_gps",
        related_peers=3,
    )
    assert boosted.score > base.score
    assert boosted.riskScore >= base.riskScore


def test_score_is_reproducible_no_randomness():
    kwargs = {
        "severity": "high",
        "confidence": "probable",
        "source": "github",
        "finding_type": "username_profile",
        "related_peers": 2,
    }
    first = score_finding(**kwargs)
    for _ in range(20):
        assert score_finding(**kwargs).to_dict() == first.to_dict()


def test_weights_change_changes_score_reproducibly():
    confident = score_finding(
        severity="medium", confidence="confirmed", source=None, finding_type=None
    )
    confidence_heavy = score_finding(
        severity="medium",
        confidence="confirmed",
        source=None,
        finding_type=None,
        weights={"confidence": 0.6, "severity": 0.2, "exposureAge": 0.0},
    )
    assert confidence_heavy.score != confident.score


def test_level_boundaries():
    assert level_for(0.99) == "critical"
    assert level_for(0.75) == "critical"
    assert level_for(0.74) == "high"
    assert level_for(0.5) == "high"
    assert level_for(0.45) == "medium"
    assert level_for(0.3) == "medium"
    assert level_for(0.2) == "low"
    assert level_for(0.15) == "low"
    assert level_for(0.1) == "negligible"
    assert level_for(0.0) == "negligible"


def test_explain_risk_is_deterministic_and_attributive():
    br = score_finding(
        severity="high",
        confidence="probable",
        source="rdap",
        finding_type="image_gps",
        related_peers=2,
    )
    text = explain_risk(br)
    assert "Deterministic score" in text
    assert str(br.riskScore) in text
    assert "confidence 75%" in text
    assert "source reliability 80%" in text
    for _ in range(5):
        assert explain_risk(br) == text


def test_explain_false_positive_explains_gate():
    br = score_finding(severity="critical", confidence="false_positive")
    assert "false_positive" in explain_risk(br)


def test_risk_breakdown_out_schema_roundtrip():
    br = score_finding(
        severity="medium",
        confidence="possible",
        source="search",
        finding_type="email_exposure",
        related_peers=1,
    )
    out = RiskBreakdownOut.model_validate(br.to_dict())
    assert out.score == br.score
    assert out.riskScore == br.riskScore
    assert out.level == br.level