# Spec: agent-api

## Objective
HTTP surface for the agent. One SSE endpoint, plus a conversation read endpoint and audit.

## Endpoints
- `POST /api/agent/chat` — SSE stream. Body `{message: str, scanId?: number|null}`.
  Emits named events: `thought`, `tool`, `result`, `evidence`, `confirm`, `error`, `done`.
  Each event is `data: {"kind": ..., "label": ..., "detail": ..., "evidence": [...]}`.
  Guard: `PG_AGENT_ENABLED` (default on) and (configurable) `PG_AGENT_ALLOW` — activation
  gates tie to the existing fightClub of hybrid/explicit approval.
- `GET /api/agent/conversations` + `GET /api/agent/conversations/{id}` — persisted
  conversation history (local DB) for audit.

## Behavior
- No AI backend → stream a single `error`/`blocked` event; never hang.
- One in-flight conversation per client; 429 on abuse (`PG_AGENT_RATE`).

## Boundaries
- **Always:** SSE contract stable; auth/approval gate before any tool runs; all steps persisted.
- **Never:** expose tool args/secrets in history; unbounded request size.