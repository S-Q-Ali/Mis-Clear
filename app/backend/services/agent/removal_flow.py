"""Confirm-gated removals from agent evidence (SPEC-removal-flow).

The agent may PROPOSE removals (confirm steps) from tool evidence. Nothing is
state-changing until the user confirms that exact item:

  approve -> a `pending` PrivacyAction (approval_required=True) is created via
             the deterministic procedure mapping; the existing Actions UI still
             requires its own approve before anything executes.
  deny    -> only an audit record, no action.

By construction no code path creates an action without a confirm event for that
item: proposals are read back from the PERSISTED conversation steps, never from
a client-supplied URL.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backend import models as m
from app.backend.services.deletion_research import DRAFT_DISCLAIMER
from app.backend.services.removal_registry import removal_channel_for
from app.backend.services.site_advisory import advisory_for
from app.backend.services.takedown_procedures import procedure_for_finding


def confirm_proposals_of(latest_agent_steps: list[dict] | None) -> list[dict]:
    """Read back the confirm proposals that were actually persisted."""
    if not latest_agent_steps:
        return []
    return [
        s.get("data") or {}
        for s in latest_agent_steps
        if isinstance(s, dict) and s.get("kind") == "confirm" and isinstance(s.get("data"), dict)
    ]


def action_from_proposal(db: Session, conversation_id: int, proposal: dict) -> m.PrivacyAction:
    """Deterministically map one confirmed proposal to a pending action."""
    url = str(proposal["url"])
    proc = procedure_for_finding(url)
    adv = advisory_for(url)
    channel = removal_channel_for(url)
    target = str(proposal.get("target") or url)
    evidence_ref = f"agent:{conversation_id}:{url}"

    existing = db.execute(
        select(m.PrivacyAction).where(m.PrivacyAction.evidence_reference == evidence_ref)
    ).scalars().first()
    if existing is not None:
        return existing  # never duplicate a confirmed removal

    org = proc.organization
    steps = "\n".join(f"- {s}" for s in proc.steps)
    advisory_line = (
        f"Site advisory: {adv['category']} "
        f"(recommended={adv['recommended'] if adv['recommended'] is not None else 'unknown'}). "
        f"{adv['rationale']}\n"
    )
    draft = (
        f"Subject: Request for removal of personal data exposure\n\n"
        f"To the privacy/support team at {org}:\n\n"
        f"I am requesting the removal of a personal data exposure associated "
        f"with my identity, referenced in my Privacy Guardian agent "
        f"investigation as '{target}' (located at: {url}).\n\n"
        f"Please confirm removal of this data in accordance with your privacy "
        f"procedures and provide confirmation.\n\n{DRAFT_DISCLAIMER}"
    )
    action = m.PrivacyAction(
        finding_id=None,
        recommended_action=f"Request removal of agent-flagged exposure '{target}' from {org}",
        deletion_url=proc.procedure_url,
        instructions=(
            f"Official organization: {org}\n"
            f"Procedure URL: {proc.procedure_url or 'not on file (verify manually)'}\n"
            f"Removal channel: {channel}\n"
            f"{advisory_line}"
            f"Steps:\n{steps}\n\nRequest draft:\n{draft}"
        ),
        evidence_reference=evidence_ref,
        approval_required=True,
        status="pending",
    )
    db.add(action)
    db.flush()
    return action