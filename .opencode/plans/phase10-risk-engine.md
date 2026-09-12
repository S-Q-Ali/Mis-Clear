# Plan — Phase 10: Risk Engine (deterministic, reproducible scores)

Controlling spec: MASTER_BUILD_INSTRUCTIONS.md §10 — risk from severity,
confidence, source reliability, data sensitivity, exposure age, correlation
strength. Deterministic rules only; AI (if ever) may *explain* the score but
never compute it. All scores reproducible from inputs.

## Design
- `app/backend/services/risk_engine.py`:
  - `DEFAULT_WEIGHTS` (must sum ~1): severity .30, confidence .25,
    sourceReliability .15, sensitivity .15, exposureAge .05, correlation .10.
    `validate_weights()` raises ValueError if sum outside tolerance.
  - Deterministic normalizations (0..1):
    - severity: informational=0, low=.25, medium=.5, high=.75, critical=1.
    - confidence: confirmed=1, probable=.75, possible=.5, weak=.25,
      false_positive=0 → **gate**: score 0 / negligible (never averages away).
    - source reliability: `SOURCE_RELIABILITY` map (github/dns/whois/rdap=.8,
      search/leak/sherlock/.65, default .5).
    - sensitivity: `SENSITIVITY` by finding type (image_gps=.9, image_qrcode=.8,
      email_exposure=.7, photo_metadata=.6, username_profile=.5, default .5).
    - exposure age: factor = 1.0 when age_days<=1, decays linear to floor .2 at
      >=292 days (unknown age defaults to 1.0 — never a fabricated age).
    - correlation: `min(1, related_peers * 0.34)` — peers = other findings of
      same type in the scan (independent confirmations).
  - `score_finding(inputs, *, weights=None)` → `RiskBreakdown` (factors + score
    0..1 + level + riskScore 0..100). Pure, injectable — fully unit-testable.
  - `explain_risk(breakdown)` → deterministic rule-based sentence attaching
    each contributing factor (satisfies "AI may explain, score reproducible").
  - `score_scan(db, scan_id, *, weights=None)` → aggregate: riskScore = max
    finding score, averageRiskScore = mean, per-finding rows sorted desc.
- API: `GET /api/scans/{id}/risk` → `ScanRiskOut` (404 missing; honest empty
  when no findings: score 0, no fabricated data). schemas: `RiskBreakdownOut`,
  `FindingRiskOut`, `ScanRiskOut`.
- No schema migration; risk is computed (derived) on demand.

## Slices
- A. `risk_engine.py` scoring core + unit tests (weights validation, factor
  normalizations, fp gate, age decay corners, correlation cap, reproducibility,
  explain output) → commit.
- B. Scan-level aggregation + API + schemas + integration tests → commit.
- C. Docs (TOOL_MATRIX note not needed; PROJECT_DOCUMENTATION list + status,
  ARCHITECTURE module row, SESSION_STATE) + full suite + push.

## Guardrails
- Synthetic fixtures only. No randomness in score path (reproducible).
- Never attribute a source reliability / age / sensitivity that isn't computed.
- AI may explain later; score engine stays rule-based.