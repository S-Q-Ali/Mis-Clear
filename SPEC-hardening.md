# Spec: hardening

## Objective
Security hardening of the agent layer: prompt-injection defense, rate limiting, approval
toggles, and doc sync (THREAT_MODEL / SECURITY_MODEL / ARCHITECTURE / PROJECT_DOCUMENTATION /
TOOL_MATRIX + SESSION_STATE).

## Controls
- **Injection suite** (`tests/security/test_agent_injection.py`): tool results that embed
  "ignore system / run shell / send secrets to X" never become instructions; allowlist
  blocks unknown tools; no URL/exec tools exist in the registry.
- **Rate limit:** `PG_AGENT_RATE` (requests/min per client) → 429.
- **Approval gate:** config to require explicit `hybrid-like` approval before agent can use
  third-party-network tools (reverse-image / breach). Local-only tools exempt.
- **No secrets:** logs redact tool args that look like secrets; history omits raw inputs.

## Boundaries
- **Always:** full gate (pytest + ruff + lint + build) before final commit; docs synced.
- **Never:** weaken existing privacy gates; commit `.env`.