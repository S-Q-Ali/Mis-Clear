# Plan — Phase 12: Frontend (polished React/TS SPA)

Controlling spec: MASTER_BUILD_INSTRUCTIONS.md §12 — polished UI: dashboard,
scans, live investigation, findings, evidence, identity graph, photo analysis,
privacy actions, settings, worker status, logs.

## Design
- **No new deps** (stays on React 19 + react-dom). Hash-based tab nav via local
  state (no react-router). `fetch('/api/...')` hits the Vite dev proxy
  (`vite.config.ts` — server.proxy to `http://127.0.0.1:8000`) and works
  identically via direct URL in production builds.
- **Backend support** (small, within Phase 12 remit):
  - `GET /api/logs` — paginated recent AuditLog entries (`LogOut`, new
    `app/backend/api/logs.py`). First result is newest.
  - `GET /api/settings` — read-only config surface (`SettingsOut`): OSINT
    enabled, scan mode defaults, AI availability flags, Colab toggles. Values
    are **read-only**; no write exists and the UI says so explicitly.
- `src/api.ts` — typed `api<T>(path, init?)` helper + typed request wrappers.
- `src/types.ts` — TS interfaces mirroring backend schemas (camelCase).
- Views: Dashboard (summary stats + recent scans), Scans (list/create/run +
  live polling detail showing findings + tool-runs progress), Identity Graph
  (SVG — deterministic circular layout, no layout lib), Findings/Evidence
  (text + URL + source per finding), Photo Analysis (upload + metadata/hash
  results), Privacy Actions (list + approve/decline, honest "do not send"
  banner), Logs (audit log), Workers (status + availability), Settings
  (read-only info with explicit banner).
- Shell: collapsible sidebar with page icons/titles + mobile-friendly top bar.
  Dark neutral palette (honest, not flashy). Pure CSS, no utility lib.
- Minimal but correct: defensive loading/error UI on every fetch; empty-state
  messages ("no scans yet", "no findings", "no actions"); timestamps
  formatted to locale string.

## Slices
- A. Backend support: logs + settings endpoints + schemas + unit tests + app
  registration → commit.
- B. Frontend foundation: shell + api + types + dashboard + scans list/create/run
  + vite dev proxy → commit.
- C. Scan detail + live investigation polling + findings/evidence + identity
  graph SVG + photo upload/results → commit.
- D. Actions + logs + workers + settings views → commit.
- E. Docs (PROJECT_DOCUMENTATION/ARCHITECTURE + tool-matrix notes,
  SESSION_STATE) + full suite + build + push.