# Plan — Phase 6: OSINT Tool Adapters (complete)

Controlling spec: `MASTER_BUILD_INSTRUCTIONS.md` Phase 6. Contract:
`run(target) -> ToolResult` with tool, status, duration, findings, errors,
raw reference, coverage.

## Status before this plan (already written to disk, uncommitted, no network run)
- `tools/base.py` — ToolAdapter ABC, ToolFinding (evidence-model validated), ToolResult
- `tools/sitecheck.py` + `tools/site_manifests/{email,username}.json` — sample-host engine (holehe/sherlock)
- `tools/email/holehe.py`, `tools/username/sherlock.py`
- `tools/web/{dns,whois,search,github}.py` — DoH / RDAP / DuckDuckGo HTML / GitHub API
- `tools/registry.py` — build_registry()/adapters_for() with client_factory injection
- `app/backend/services/scan_orchestrator.py` — persists ToolRun + Finding + Identity

## Remaining steps

### 1. Config + env
- `app/backend/config.py`: add
  `osint_enabled: bool = True`, `osint_timeout_seconds: float = 10.0`,
  `osint_manifest_email`, `osint_manifest_username` (paths to packaged samples)
- `.env.example`: add `# --- OSINT ---` section with the four vars

### 2. API: run endpoint
- `app/backend/api/scans.py`: `POST /api/scans/{scan_id}/run`
  - body optional `{"tools": ["holehe", ...]}` filter (None = all matching)
  - 404 if scan missing; calls `run_scan(db, scan, tool_filter=...)`; returns `ScanOut`
  - synchronous; bounded by small manifests + 10s per-tool timeout (worker = Phase 8)

### 3. Tests (fake transport ONLY — zero real network)
- `tests/unit/test_osint_adapters.py` (httpx.MockTransport):
  - dns: records → informational finding; NXDOMAIN-like empty → completed, no finding; HTTP error → failed
  - whois/rdap: 200 JSON → confirmed registration finding; 404 → completed no finding
  - search: DDG HTML fixture → weak findings parsed, raw_reference = query url
  - github: user 200 → confirmed; 404 → completed no finding; email search items → probable
  - sitecheck email mode: exists marker → probable finding, missing marker → none, POST form field used
  - sitecheck username mode: marker + 200 → probable; 404 → absent
  - registry: adapters_for filters; default registry set incl. sample manifests
  - base: invalid confidence/severity raises ValueError
- `tests/integration/test_scan_run.py`:
  - orchestrator unit: fake adapters (registry injected) → ToolRun/Finding/Identity rows,
    scan running→completed, coverage aggregate, tool_filter honored
  - API: POST scan → POST run (monkeypatch build_registry → fake adapters) → status completed + findings visible
- `tests/unit/test_database.py` unaffected

### 4. Verify
- `uv run pytest` (expect ~40+ green), legacy 46+34, `npm run build`

### 5. Docs + tracking
- `docs/TOOL_MATRIX.md`: Phase 6 rows → ✅ implemented (holehe/sherlock manifests = configurable sample hosts)
- `docs/PROJECT_DOCUMENTATION.md`: Phase 6 ✅ + current implementation bullets
- `docs/ARCHITECTURE.md`: module map tool adapters + orchestrator ✅
- `SESSION_STATE.md`: Phase 6 entry

### 6. Commit + push
- `feat: phase 6 - OSINT tool adapters (email/username/web) + scan orchestrator + run endpoint`
- `git push origin main`

## Guardrails
- No real personal data in tests (synthetic only)
- Web content = untrusted input; adapters never execute page content
- Coverage is honest (sources_total/checked/failed); sample manifests are synthetic
- Do NOT modify `.opencode/opencode.json` (unrelated $schema change stays out unless asked)