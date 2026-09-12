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
- **URL safety guardrail** (`app/backend/security/url_safety.py`):
  `https`-only, no userinfo, private/loopback/reserved IP literals and
  private hostname families (`localhost`, `*.local`, `*.internal`,
  metadata names) rejected. Manifest `probe_url` templates must not place
  the `{target}` placeholder in the authority, and the formatted URL is
  checked to remain on the manifest's host.
- **Evidence central cap**: `ToolFinding.evidence` is truncated to 2000 chars
  (defense-in-depth against unbounded web payloads and DB bloat).
- **Security response headers**: every API response carries
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, `Content-Security-Policy: default-src 'none'`;
  `/api/*` responses also include `Cache-Control: no-store`.

## AI routing safety
- Sensitive prompts never leave the laptop unless the user explicitly approves
  HYBRID mode for that data.
- `ModelRouter` uses Colab only when approved AND available; `strict_local`
  mode forbids Colab entirely.
- No AI backend available is a valid state: the app degrades, it never
  substitutes a weaker cloud model silently.

## Transport
- Backend binds `127.0.0.1` only unless the user explicitly enables otherwise.
- CORS restricted to local Vite origin by default.

## Upload safety
- Size cap (`PG_UPLOAD_MAX_BYTES`, default 20 MB) plus magic-byte validation
  (Pillow `verify`).
- Decompression-bomb guard: declared `width × height` must not exceed
  `PG_UPLOAD_MAX_PIXELS` (default 50 MP) — checked from the header before any
  pixel allocation.
- Stored filenames are server-generated (`<scan_id>_<uuid>.<safe_ext>`); the
  display name is a stripped basename. Uploaded paths can never leave the
  upload directory (path-traversal tested for `/`, `%2F`, and `\` inputs).

## Access
- Local single-user app; no remote auth surface in default mode.
- Write surfaces are minimal and guarded: `/api/settings` is read-only (405 on
  POST/PUT/PATCH/DELETE); privacy-action transitions only apply to `pending`;
  idempotency keys cannot be reused with a different payload.
- Secret scanning before any commit.

## Verification state (2026-09-12)
- `uvx pip-audit` → **0 known vulnerabilities**; `npm audit` (prod + dev) →
  **0 vulnerabilities**.
- Secret scan over tracked files (git grep): only benign matches (doc prose,
  test fixtures, URL regexes).
- 55 security tests in `tests/security/` covering the list above.

See also `docs/THREAT_MODEL.md`.