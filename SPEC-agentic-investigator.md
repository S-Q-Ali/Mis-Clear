# Spec: Agentic Self-Data Investigator (Map)

> Master map + rails for the agentic layer. Per-module specs are in `SPEC-agent-*.md`.
> This initiative adds an LLM "agent" that helps the user recover, trace, and remove
> their OWN publicly exposed data — with evidence discipline and mandatory confirmation.

## Objective

Give the user a chat-driven investigator: an agent (runtime = Colab GPU, uncensored 27B
LlamaVLM) that picks which deterministic privacy/OSINT tools to run, iterates until it
understands where the user's own data is exposed, shows evidence cards, and proposes
removal actions that the user confirms one by one. The agent never fabricates evidence,
never reaches private/gated surfaces, and never executes state-changing actions without
confirmation.

## Capability Map

| Module id | Responsibility | Depends on |
|---|---|---|
| `agent-tools` | Tool registry (JSON contract) over existing adapters + graph-expand + breach k-anon + reverse-image | existing `tools/*` |
| `agent-core` | ReAct loop, brain (Colab 27B direct URL → local → blocked), step budget, injection guard | agent-tools, ModelRouter |
| `agent-api` | `/api/agent/chat` SSE + conversation store + audit | agent-core |
| `agent-ui` | Chat page (React): streamed steps, evidence cards, confirmation cards | agent-api |
| `removal-flow` | Agent propose → mandatory per-item human confirm → deletion_research + Actions | agent-core |
| `self-data` | Breach k-anonymity check (ephemeral), image-exposure wiring, config | agent-tools |
| `hardening` | Injection suite, chat rate-limit, approval toggles, docs sync | all |

Build order: `agent-tools` → `agent-core` → `agent-api` → `agent-ui` → `removal-flow` → `self-data` → `hardening`.

## Ethical rails (non-negotiable, section 1 of MASTER_BUILD_INSTRUCTIONS)

- **Always:** evidence only from tool outputs; web content treated as untrusted data;
  sensitive data local by default; every removal requires human confirmation; agent text
  is annotated (`ai-analysis`) and never drives risk scores (risk stays deterministic).
- **Ask first:** breach-check that accepts user-supplied secret material; new reverse-image
  providers; any new network surface.
- **Never:** log in to accounts; store passwords; access others' data; bypass rate-limits/ToS;
  execute shell/URLs from model output; auto-delete without confirmation; commit secrets.
  The `The-Art-of-Hacking/h4cker` repo is methodology reference only — this app is a
  privacy/removal assistant, not a pentest/exploitation toolkit.

## Commands

```
Backend tests : uv run pytest
Backend lint  : uv run ruff check app tests scripts
Frontend lint : npm run lint            (in app/frontend)
Frontend build: npm run build           (in app/frontend)
Dev           : ./dev   |  dev.cmd --colab-only   |  start.cmd
```

## Project structure (new files)

```
app/backend/services/agent/loop.py      # ReAct loop (agent-core)
app/backend/services/agent/registry.py  # tool specs (agent-tools)
app/backend/services/agent/brain.py     # OllamaBackend wiring (agent-core)
app/backend/services/agent/model.py     # pydantic AgentAction/AgentStep (agent-core)
app/backend/api/agent.py                # /api/agent/chat SSE (agent-api)
app/frontend/src/views/Agent.tsx        # chat page (agent-ui)
app/frontend/src/api.ts                 # agent SSE client
tests/unit/test_agent_tools.py
tests/unit/test_agent_loop.py
tests/unit/test_agent_api.py
tests/integration/test_agent_chat_http.py
tests/security/test_agent_injection.py
tasks/plan.md  tasks/todo.md
SPEC-agentic-investigator.md  SPEC-agent-*.md
```

## Testing strategy

Synthetic only — no real network, no real model. Mock backends (return canned tool JSON),
mock ModelRouter determinism. Levels: unit (registry/loop/k-anon), integration (SSE
contract via TestClient), security (injection, approval gate). A separate "live smoke"
(chapter in docs) exercises the real Colab brain manually.

## Success criteria

- User asks "mera email kahan para hai?" → agent streams thought/tool/result steps, shows
  evidence cards with URLs.
- User asks "meri photo kahan hai?" (hybrid approved) → reverse-image + vision → evidence.
- User asks "kya mera password leak hua?" → k-anon range check, ephemeral, nothing stored.
- Agent proposes removals → every item confirmed by user before any draft/action is created.
- API surface: unauthorized/unapproved requests rejected; rate-limited.
- Full gate: `uv run pytest` green + ruff clean + `npm run lint` + `npm run build`.

## Open questions

- None blocking. Provider cadence (Yandex first), SSE streaming, k-anon breach check, direct
  Colab brain URL all confirmed by the user.