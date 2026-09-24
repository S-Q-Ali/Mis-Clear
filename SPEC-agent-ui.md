# Spec: agent-ui

## Objective
A separate chat page (sidebar "Agent") that renders the SSE stream: user prompt, agent
thought cards, tool-call cards with results, evidence cards (URLs/verbatim), confirmation
cards for removals, and a terminal answer. No polling — EventSource/SSE driven.

## Behavior
- Input box + send; streaming timeline replaces the naive refresh model.
- Evidence card: source label, URL (non-executed, `<a>` open-in-new-tab), verbatim quote.
- Confirm card: "Remove X from Y?" → Approve / Deny → calls removal confirm endpoint (S5).
- Blocked state (no brain) renders an honest banner, not fabrications.

## Boundaries
- **Always:** accessible & keyboard-friendly form; clear blocked/error states.
- **Never:** auto-approve; render untrusted content as anything but inert text; execute URLs.