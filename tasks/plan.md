# Build Plan: Agentic Self-Data Investigator

Build order per SPEC-agentic-investigator.md. Each slice: TDD (red→green), ruff, commit, push.

## Plan

1. **agent-tools** — registry of ToolSpec wrappers over existing adapters + k-anon breach
   check helper. Unit tests (strict JSON, block/fail mapping, k-anon no-storage).
2. **agent-core** — action/model schemas, ReAct loop, brain resolver (Colab direct → local →
   blocked), injection guard. Unit tests (budget, JSON recovery, tool-only findings).
3. **agent-api** — `POST /api/agent/chat` SSE + conversation store + audit. Integration tests.
4. **agent-ui** — chat page with streamed timeline, evidence/confirm cards. lint+build.
5. **removal-flow** — propose→confirm→create_action; security test (no confirm -> no action).
6. **self-data** — wire breach config + image exposure into agent tools; `.env` docs.
7. **hardening** — injection suite, rate limit, approval toggles, docs sync, full gate.

## Risks & mitigations

- **Cloudflare/Colab tunnel flaky** → agent brain blocked gracefully; old pipeline intact.
- **27B slow on Colab** → step budget + per-step timeout; streaming keeps UX alive.
- **Prompt injection via web evidence** → untrusted wrapper + allowlist + security tests.
- **Scope creep** → strict module boundaries; each slice gated by tests.

## Verification checkpoints

- After slices 1–2: unit+ruff green.
- After 3: SSE integration green.
- After 4: frontend lint+build green.
- After 5–6: security + integration green, live smoke doc updated.
- S7: full suite + docs sync + push.