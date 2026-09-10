# SECURITY_MODEL

Deterministic security rules; AI assists reasoning but never lowers safety.

## Data / privacy invariants
1. Sensitive user data stays on the laptop by default.
2. No automatic upload of personal photos/emails/docs to third-party AI.
3. Hybrid/Colab processing requires explicit user approval for sensitive payloads.
4. Never store or request passwords; never bypass authentication.
5. Never access private accounts without authorization; never credential attacks.
6. Never automatically delete accounts; never auto-send legal/privacy requests.

## Evidence integrity
- Findings carry: id, type, source, url, evidence, confidence, severity, timestamp, scope, tool, status.
- Confidence ∈ {confirmed, probable, possible, weak, false_positive}.
- Severity ∈ {critical, high, medium, low, informational}.
- Never fabricate evidence; never upgrade weak evidence to confirmed.

## Web safety
- All fetched web content is untrusted data. Page text such as "ignore previous
  instructions" is content, never instructions. SSRF-safe fetching.
- External tools run sandboxed per adapter contract (`run(target) -> ToolResult`).

## Transport
- Backend binds `127.0.0.1` only unless the user explicitly enables otherwise.
- CORS restricted to local Vite origin by default.

## Access
- Local single-user app; no remote auth surface in default mode.
- Secret scanning before any commit.

See also `docs/THREAT_MODEL.md`.