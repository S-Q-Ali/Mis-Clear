# Spec: removal-flow

## Objective
The agent may PROPOSE removals from evidence, but nothing state-changing happens until the
user confirms that exact item. Reuses `deletion_research.create_action` (official
procedures, evidence reference, approval_required=True).

## Contract
- Agent step kind `confirm` carries `{target, org, url, evidence}`.
- `POST /api/agent/confirm` body `{conversationId, itemIndex, decision: approve|deny}`.
  - approve → create a `pending` PrivacyAction via `deletion_research` (status stays
    `pending`; the existing Actions UI still requires its own approve to execute).
  - deny → no action created; logged.
- No confirm → no action. Any code path that creates an action without a human confirm
  event for that item is a bug (security test asserts this).

## Boundaries
- **Always:** every removal = explicit user confirmation at the item level; audit both
  events; deterministic mapping from evidence to procedure.
- **Never:** auto-create removal; batch-confirm; delete without the existing action approval.