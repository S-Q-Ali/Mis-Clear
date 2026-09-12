"""Deterministic risk engine (Phase 10, master plan §10) — rules only, no AI.

Scores are 0..1 composites of six factors (severity, confidence, source
reliability, data sensitivity, exposure age, correlation strength). Fully
reproducible from inputs; the engine never invents a missing value (unknown
age/reliability/sensitivity fall back to fixed neutral constants).

AI may later *explain* a score (`explain_risk`) but never compute it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

SEVERITY_WEIGHTS: dict[str, float] = {
    "informational": 0.0,
    "low": 0.25,
    "medium": 0.5,
    "high": 0.75,
    "critical": 1.0,
}

CONFIDENCE_WEIGHTS: dict[str, float] = {
    "confirmed": 1.0,
    "probable": 0.75,
    "possible": 0.5,
    "weak": 0.25,
    "false_positive": 0.0,
}

SOURCE_RELIABILITY: dict[str, float] = {
    "github": 0.8,
    "rdap": 0.8,
    "whois": 0.8,
    "dns": 0.8,
    "search": 0.65,
    "leak": 0.65,
    "sherlock": 0.65,
    "holehe": 0.65,
}
SOURCE_RELIABILITY_DEFAULT = 0.5

SENSITIVITY: dict[str, float] = {
    "image_gps": 0.9,
    "image_qrcode": 0.8,
    "email_exposure": 0.7,
    "photo_metadata": 0.6,
    "image_exif": 0.6,
    "username_profile": 0.5,
}
SENSITIVITY_DEFAULT = 0.5

EXPOSURE_AGE_DECAY_DAYS = 292.0  # linear to floor
EXPOSURE_AGE_FLOOR = 0.2
CORRELATION_PEERS_TO_FULL = 3.0

LEVELS: list[tuple[str, float]] = [
    ("critical", 0.75),
    ("high", 0.5),
    ("medium", 0.3),
    ("low", 0.15),
    ("negligible", 0.0),
]

DEFAULT_WEIGHTS: dict[str, float] = {
    "severity": 0.30,
    "confidence": 0.25,
    "sourceReliability": 0.15,
    "sensitivity": 0.15,
    "exposureAge": 0.05,
    "correlation": 0.10,
}
_WEIGHT_TOL = 0.01


def validate_weights(weights: dict[str, float] | None) -> dict[str, float]:
    """Merge over defaults, normalize to sum 1. Unknown keys rejected.

    Deterministic + reproducible: partial overrides are rescaled so the six
    factors always add up to a 0..1 composite.
    """
    merged = {**DEFAULT_WEIGHTS, **(weights or {})}
    if set(merged) != set(DEFAULT_WEIGHTS):
        raise ValueError(f"unknown weight keys: {set(merged) ^ set(DEFAULT_WEIGHTS)}")
    total = sum(merged.values())
    if abs(total - 1.0) > _WEIGHT_TOL:
        merged = {k: v / total for k, v in merged.items()}
    return merged


def severity_factor(severity: str) -> float:
    return SEVERITY_WEIGHTS.get(severity or "", SEVERITY_WEIGHTS["low"])


def confidence_factor(confidence: str) -> float:
    return CONFIDENCE_WEIGHTS.get(confidence or "", 0.0)


def source_reliability(source: str | None) -> float:
    key = (source or "").strip().lower()
    for known, value in SOURCE_RELIABILITY.items():
        if known in key:
            return value
    return SOURCE_RELIABILITY_DEFAULT


def sensitivity_factor(finding_type: str | None) -> float:
    return SENSITIVITY.get(finding_type or "", SENSITIVITY_DEFAULT)


def exposure_age_factor(age_days: float | None) -> float:
    """Unknown age → 1.0 (never fabricated); otherwise linear decay to floor."""
    if age_days is None or age_days <= 1.0:
        return 1.0
    return max(EXPOSURE_AGE_FLOOR, 1.0 - (age_days - 1.0) / EXPOSURE_AGE_DECAY_DAYS)


def correlation_factor(related_peers: int) -> float:
    return min(1.0, max(0, int(related_peers)) * (1.0 / CORRELATION_PEERS_TO_FULL))


def level_for(score: float) -> str:
    for name, threshold in LEVELS:
        if score >= threshold:
            return name
    return "negligible"


@dataclass
class RiskBreakdown:
    severity: float
    confidence: float
    sourceReliability: float
    sensitivity: float
    exposureAge: float
    correlation: float
    score: float
    riskScore: int
    level: str
    gated: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def score_finding(
    *,
    severity: str,
    confidence: str,
    source: str | None = None,
    finding_type: str | None = None,
    age_days: float | None = None,
    related_peers: int = 0,
    weights: dict[str, float] | None = None,
) -> RiskBreakdown:
    """Deterministic composite score for one finding. Pure — no I/O, no random."""
    w = validate_weights(weights)
    conf = confidence_factor(confidence)

    # false_positive gate: a false positive always scores 0 (never masked by other factors).
    if confidence == "false_positive":
        return RiskBreakdown(
            severity=severity_factor(severity),
            confidence=0.0,
            sourceReliability=source_reliability(source),
            sensitivity=sensitivity_factor(finding_type),
            exposureAge=exposure_age_factor(age_days),
            correlation=correlation_factor(related_peers),
            score=0.0,
            riskScore=0,
            level="negligible",
            gated=True,
        )

    sev = severity_factor(severity)
    rel = source_reliability(source)
    sens = sensitivity_factor(finding_type)
    age = exposure_age_factor(age_days)
    corr = correlation_factor(related_peers)

    composite = (
        w["severity"] * sev
        + w["confidence"] * conf
        + w["sourceReliability"] * rel
        + w["sensitivity"] * sens
        + w["exposureAge"] * age
        + w["correlation"] * corr
    )
    composite = min(1.0, max(0.0, composite))
    return RiskBreakdown(
        severity=sev,
        confidence=conf,
        sourceReliability=rel,
        sensitivity=sens,
        exposureAge=age,
        correlation=corr,
        score=round(composite, 4),
        riskScore=round(composite * 100),
        level=level_for(composite),
    )


def explain_risk(br: RiskBreakdown) -> str:
    """Deterministic rule-based explanation attributing each factor (no AI call)."""
    if br.gated:
        return "Finding marked false_positive — risk ignored (deterministic gate)."
    parts = [
        f"severity {br.severity * 100:.0f}%",
        f"confidence {br.confidence * 100:.0f}%",
        f"source reliability {br.sourceReliability * 100:.0f}%",
        f"data sensitivity {br.sensitivity * 100:.0f}%",
        f"exposure age factor {br.exposureAge * 100:.0f}%",
        f"correlation {br.correlation * 100:.0f}%",
    ]
    return f"Deterministic score {br.riskScore}/100 (level {br.level}); factors: {', '.join(parts)}."


def score_scan(db, scan_id: int, *, weights: dict[str, float] | None = None) -> dict[str, Any]:
    """Aggregate risk for a scan. Derived on demand; never persisted/fabricated.

    Correlation = other findings of the same type in this scan (independent
    confirmations). returns per-finding breakdowns sorted by score desc.
    """
    from sqlalchemy import select

    from app.backend import models as m

    findings = db.execute(
        select(m.Finding).where(m.Finding.scan_id == scan_id)
    ).scalars().all()

    peers: dict[str, int] = {}
    for f in findings:
        peers[f.type] = peers.get(f.type, 0) + 1

    rows = []
    for f in findings:
        br = score_finding(
            severity=f.severity,
            confidence=f.confidence,
            source=f.source,
            finding_type=f.type,
            age_days=None,
            related_peers=peers.get(f.type, 1) - 1,
            weights=weights,
        )
        rows.append({
            "findingId": f.id,
            "type": f.type,
            "title": f.title,
            "score": br.score,
            "riskScore": br.riskScore,
            "level": br.level,
            "breakdown": br.to_dict(),
        })
    rows.sort(key=lambda r: r["score"], reverse=True)

    if not rows:
        return {
            "scanId": scan_id,
            "riskScore": 0,
            "level": "negligible",
            "averageRiskScore": 0,
            "findingCount": 0,
            "findings": [],
        }
    top = rows[0]
    average = sum(r["score"] for r in rows) / len(rows)
    return {
        "scanId": scan_id,
        "riskScore": top["riskScore"],
        "level": top["level"],
        "averageRiskScore": round(average * 100),
        "findingCount": len(rows),
        "findings": rows,
    }