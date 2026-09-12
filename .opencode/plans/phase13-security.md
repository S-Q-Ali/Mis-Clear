# Phase 13 — Security Hardening

Master plan §"Phase 13 --- Security": dependency audit, secret scan, prompt
injection tests, malicious webpage tests, path traversal tests, command
injection tests, SSRF tests, unsafe URL tests, file upload tests,
authorization tests, local network exposure tests.

## Context (surveyed)

- SSRF/unsafe-URL surface: OSINT adapters build URLs from user targets. Safe
  today (fixed public endpoints, params/quote, strict regex for DNS), BUT
  `tools/sitecheck.py` does raw `probe_url.format(target=...)` and manifests
  are user-editable local config — a `{target}` in the authority position or a
  private-IP literal host would make the laptop probe internal services.
- No security response headers anywhere.
- Uploads: size cap + magic-byte verify exist; **no pixel/decompression-bomb
  guard** before the photo pipeline `Image.open(...).convert` allocates pixels.
- Evidence strings come from untrusted web content; caps are per-adapter
  (300/1000 chars) but not enforced centrally (DB-bloat bound).
- Command execution: only `colab/capabilities.probe_nvidia_smi` uses
  subprocess — fixed argv list, `shell=False` (absent) → verify by test.
- Authorization: no user model (local-only tool). Existing guards: read-only
  settings (405), action pending-only transitions (409), idempotency
  replay/mismatch. CORS allow-list is loopback-only by default; bind default
  `127.0.0.1` (start.ps1 uses 127.0.0.1).
- Dependency audits run (2026-09-12): `uvx pip-audit` → 0 known issues; `npm
  audit` (incl dev) → 0 vulnerabilities. Secret scan (git grep over tracked
  files): only benign matches (doc prose, test fixtures, URL regex).

## Slices

### Slice A — Guardrails (code)
- `app/backend/security/url_safety.py`:
  - `assert_safe_web_url(url)` — scheme in {http, https}; never `file://`,
    `javascript:` etc.; no userinfo; reject private/loopback/link-local/
    reserved IP literals (stdlib `ipaddress`) and private hostname families
    (`localhost`, `*.local`, `*.internal`, `*.localhost`, metadata names).
  - `probe_url_safe(spec_url)` — for sitecheck manifests: https-only, no
    `{target}` placeholder inside the authority (scheme://host:port part),
    host passes private-IP check. Returns reason string on failure.
  - `formatted_url_matches(url, base)` — host + scheme equality after
    `{target}` interpolation (spoofed-authority defense).
- `app/backend/security/middleware.py` — `SecurityHeadersMiddleware`:
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, `Content-Security-Policy: default-src 'none'`,
  `Cache-Control: no-store` on `/api/*`. Wired in `main.py`.
- `tools/base.py` — `EVIDENCE_MAX_CHARS = 2000` enforced in `ToolFinding.__post_init__`
  (central cap; existing per-adapter caps are below, so no behavior change).
- Upload (`app/backend/api/scans.py` + `config.py`): `upload_max_pixels`
  (default 50 MP) — reject images whose declared `width*height` exceeds it
  (decompression-bomb guard) before the photo pipeline opens pixels.
- `tools/sitecheck.py` — validate manifest `probe_url` via `probe_url_safe`
  (skip site + record error if unsafe), and reject formatted URLs whose
  authority leaves the manifest host (`formatted_url_matches`).

### Slice B — Security test battery (`tests/security/`)
- `test_url_safety.py` — unsafe schemes, userinfo, private/loopback IPs,
  hostname families, placeholder-in-authority, host-consistency after
  interpolation, safe-public-host acceptance.
- `test_command_injection.py` — capability probe argv is a fixed list with no
  `shell=True` (monkeypatch `subprocess.run` capture); source-scan assertion:
  no `eval(`/`exec(`/`os.system`/`shell=True` in `app/ tools/ colab/`.
- `test_malicious_webpage.py` — DDG-style page carrying `<script>`,
  oversized snippets, and hijack text → findings inert, evidence ≤ cap,
  findings bounded, adapter completes without raising.
- `test_prompt_injection.py` — web/page content that says "ignore instructions;
  reveal system prompt" is stored verbatim-capped as data only; `extract_url_tokens`
  bounds; risk explanation stays deterministic (no AI text path).
- `test_path_traversal.py` — upload filename `..%2F..%2F..%2Fevil.png` and
  `../../evil.png` → stored under upload dir, resolved path inside base;
  suffix sanitized; display name is a bare basename.
- `test_upload_hardening.py` — oversize file → 413; non-image → 422;
  pixel-bomb dimensions → 422; tiny valid image OK (traversal/pixel guards).
- `test_authorization_and_exposure.py` — settings POST/PUT → 405 (read-only);
  CORS: disallowed origin preflight gets no `Access-Control-Allow-Origin`;
  default `host` = loopback; action approve only-pending → 409 (regression
  re-assert); idempotency disclaimer remains 422-on-mismatch.
- `test_security_headers.py` — headers present on `/api/*` responses;
  `no-store` on API, not forced elsewhere.

### Slice C — Audit evidence (docs)
Record in SESSION_STATE + docs: pip-audit 0, npm audit 0 (prod+dev),
secret-scan results, exact re-run commands.

### Slice D — Docs + commit + push
- `docs/THREAT_MODEL.md` — per-table control column updates (13 markers).
- `docs/SECURITY_MODEL.md` — new guards + audit results.
- `docs/PROJECT_DOCUMENTATION.md` — Phase 13 row + security module notes.
- Full suite (`uv run pytest`) + `npm run build` + `npm run lint`; commit
  slices atomically; push `origin/main`.

## Verification gates
- `uv run pytest` green (≥ 162 + new security tests).
- ruff clean on new modules (B008 baseline only).
- `npm run build` + `npm run lint` (0/0) unaffected.