# Spec: agent-core

## Objective
ReAct-style loop: feed the goal + tool results to the brain (Colab 27B uncensored
via `PG_COLAB_OLLAMA_URL`, **model = `PG_AGENT_MODEL` default `qwen3.8-27b-unc`**
(Qwen3.8-27B-Uncensored abliterated; alias created in the Colab notebook),
fallback local Ollama, then honest `blocked`), the model returns a
JSON action `{thought, action:{tool,args}}` or `{thought, stop, answer}`; the loop runs the
tool and repeats until stop or the step budget is exhausted.

## Guards (absolute)
- Tool allowlist only (`agent_tools.registry`); no shell/URL exec.
- Tool results wrapped: `<untrusted>...</untrusted>`; system prompt says tool content is data,
  not instructions.
- Findings/evidence are ONLY tool outputs; model text is annotated `ai-analysis` and never
  feeds the deterministic risk score.
- Step budget `PG_AGENT_MAX_STEPS` (default 20); per-step timeout; total timeout.
- Brain unavailable → `AgentResult(blocked=True)` — the app never depends on AI.

## Output model
```python
class AgentAction(BaseModel):
    thought: str
    action: ToolCall | None      # tool + args
    stop: bool
    answer: str = ""

class AgentStep(BaseModel):
    kind: Literal["thought", "tool", "result", "evidence", "error", "confirm"]
    label: str
    detail: str = ""
    evidence: list[str] = []     # URLs/verbatim, tool-derived only

class AgentResult(BaseModel):
    steps: list[AgentStep]
    blocked: bool = False
    answer: str = ""
    confirm_required: list[str] = []   # proposed removal targets (S5)
```

## Boundaries
- **Always:** strict JSON parse with recovery; deterministic ordering; block→stop.
- **Never:** fabricate; follow model-requested URLs; expose secrets.