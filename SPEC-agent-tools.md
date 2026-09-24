# Spec: agent-tools

## Objective
A tool registry the agent can call. Each tool is a spec (name, description, args schema,
cost label) plus a runner that invokes an existing deterministic adapter and returns
**strict JSON** (never arbitrary model text). Tools are read-only. All web content they
return is treated as untrusted data by the consumer.

## Tools (phase 1)
- `email_lookup` (HoleheAdapter) · `username_lookup` (SherlockAdapter) · `web_search` ·
  `dns` · `whois` · `github_user` · `site_check` · `photo_vision` (hybrid/local) ·
  `photo_nsfw` (worker) · `photo_reverse_search` (Yandex, hybrid-approved only) ·
  `graph_expand` (new candidates from a finding set) · `breach_check` (k-anon, ephemeral).

## Contract
```python
@dataclass
class ToolSpec:
    name: str
    description: str                # for the model to choose tools
    args: dict                      # json-schema-lite: {name: {type, desc, required}}
    run: Callable[..., dict]        # returns {"ok": bool, "note": str, **payload}
```
Runner failures return `{"ok": false, "note": ...}` — never raise into the loop.

## Boundaries
- **Always:** strict JSON; blocked/failed adapters become `{"ok": false}`; k-anon breach
  check computes SHA-1, truncates to 5 hex, queries a range endpoint, stores nothing.
- **Ask first:** any new network adapter/provider.
- **Never:** shell execution; following untrusted URLs; plaintext password storage.

## Verify
`uv run pytest tests/unit/test_agent_tools.py` · `uv run ruff check app tests`