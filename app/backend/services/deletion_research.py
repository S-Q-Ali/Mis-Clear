"""Deletion research (Phase 11, master plan §11) — deterministic, no AI.

For each confirmed public exposure (finding) we produce a PrivacyAction row:
official organization, official privacy/delete procedure URL (only when a
curated record exists — never fabricated), step-by-step explanation, and a
DRAFT removal request. Every action requires human approval; nothing in this
module ever sends anything.

Unknown domains take an honest path: organization = hostname-derived label,
procedure unknown, verification guidance instead of invented steps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

from app.backend import models as m
from app.backend.models import _utcnow
from app.backend.services.site_advisory import advisory_for

CANDIDATE_CONFIDENCE = {"confirmed", "probable"}
CANDIDATE_SEVERITY = {"critical", "high", "medium"}

DRAFT_DISCLAIMER = (
    "DRAFT — prepared by Privacy Guardian. Requires your personal review and "
    "approval. Do not send automatically."
)


@dataclass
class Procedure:
    domain: str
    organization: str
    procedure_url: str | None
    steps: list[str]
    known: bool = True
    extra: dict[str, Any] = field(default_factory=dict)


# Curated official procedures for well-known services (stable, real URLs).
DELETION_PROCEDURES: dict[str, Procedure] = {
    "github.com": Procedure(
        domain="github.com",
        organization="GitHub, Inc.",
        procedure_url="https://docs.github.com/en/account-and-profile/setting-up-and-managing-your-github-user-account/managing-your-personal-account/deleting-your-personal-account",
        steps=[
            "Log in to the account found in the evidence.",
            "Open Settings -> Account -> Delete account (warning dialog).",
            "Confirm the deletion and complete the required confirmation steps.",
        ],
    ),
    "reddit.com": Procedure(
        domain="reddit.com",
        organization="Reddit, Inc.",
        procedure_url="https://support.reddithelp.com/hc/en-us/articles/360043509051-How-do-I-delete-my-account",
        steps=[
            "Log in on reddit.com, open the account deletion flow.",
            "Select 'Deactivate account' and follow the confirmation prompts.",
            "Back up any data you want to keep first; deletion is permanent.",
        ],
    ),
    "x.com": Procedure(
        domain="x.com",
        organization="X Corp.",
        procedure_url="https://help.x.com/en/managing-your-account/how-to-deactivate-your-account",
        steps=[
            "Log in on x.com and open Settings -> Account.",
            "Use 'Deactivate your account' (deactivation is reversible; deletion follows later).",
            "For permanent removal, keep the account deactivated and complete the requested final steps.",
        ],
    ),
    "facebook.com": Procedure(
        domain="facebook.com",
        organization="Meta Platforms, Inc.",
        procedure_url="https://www.facebook.com/help/224562897555674",
        steps=[
            "Log in on facebook.com, open Settings & privacy -> Settings.",
            "Choose 'Accounts Center' -> 'Personal details' -> 'Account ownership and control' -> 'Deactivation or deletion'.",
            "Select 'Delete account' and confirm deletion.",
        ],
    ),
    "instagram.com": Procedure(
        domain="instagram.com",
        organization="Meta Platforms, Inc.",
        procedure_url="https://help.instagram.com/370452623149242",
        steps=[
            "Log in on instagram.com.",
            "Open Settings -> Accounts Center -> Personal details -> Account ownership and control -> Deactivation or deletion.",
            "Select 'Delete account', pick a reason, and confirm.",
        ],
    ),
    "linkedin.com": Procedure(
        domain="linkedin.com",
        organization="LinkedIn Corporation",
        procedure_url="https://www.linkedin.com/help/linkedin/answer/63",
        steps=[
            "Log in on linkedin.com.",
            "Open Me -> Settings & Privacy -> Login & security (or Account preferences).",
            "Choose 'Close account' and confirm the closing.",
        ],
    ),
}

UNKNOWN_STEPS = [
    "No curated procedure is on file for this domain.",
    (
        "Verify the identity of the official service and locate its official "
        "support/safety/privacy page before doing anything."
    ),
    (
        "Follow the service's official account/profiles deletion or personal-data "
        "removal flow, and keep a dated record of your request."
    ),
]


def _hostname_of(url: str | None) -> str | None:
    if not url:
        return None
    for prefix in ("https://", "http://", "ftp://"):
        if url.startswith(prefix):
            url = url[len(prefix):]
            break
    url = url.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if not url:
        return None
    return url


def _base_domain(hostname: str) -> str:
    parts = hostname.lower().rstrip(".").split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return hostname.lower()


def is_candidate(finding: m.Finding) -> bool:
    """Deterministic rule: confirmed/probable, meaningful severity, has URL, open."""
    return (
        finding.confidence in CANDIDATE_CONFIDENCE
        and finding.severity in CANDIDATE_SEVERITY
        and bool(finding.url)
        and finding.status == "open"
    )


def find_procedure(finding: m.Finding) -> Procedure:
    hostname = _hostname_of(finding.url)
    domain = _base_domain(hostname) if hostname else ""
    known = DELETION_PROCEDURES.get(domain)
    if known:
        return known
    return Procedure(
        domain=domain or "unknown",
        organization=(hostname or "unknown").lower(),
        procedure_url=None,
        steps=list(UNKNOWN_STEPS),
        known=False,
    )


def prepare_request(finding: m.Finding, proc: Procedure) -> str:
    url = finding.url or proc.procedure_url or "(no public URL recorded)"
    verdict = "Unknown service on file." if not proc.known else ""
    return (
        f"{verdict}\n" if verdict else ""
    ) + (
        f"Subject: Request for removal of personal data exposure\n\n"
        f"To the privacy/support team at {proc.organization}:\n\n"
        f"I am requesting the removal of a personal data exposure associated "
        f"with my identity, referenced in my Privacy Guardian investigation "
        f"as '{finding.title}' (type: {finding.type}, reference: "
        f"#{finding.id}, located at: {url}, evidence: "
        f"{finding.evidence or 'see report'}).\n\n"
        f"Please confirm removal of this data in accordance with your privacy "
        f"procedures and provide confirmation.\n\n{DRAFT_DISCLAIMER}"
    )


def research_finding(db, finding: m.Finding) -> m.PrivacyAction:
    """Get-or-create a pending action for one finding. Never clobbers a
    non-pending action (approved/declined/completed stay untouched)."""
    existing = db.execute(
        select(m.PrivacyAction).where(m.PrivacyAction.finding_id == finding.id)
    ).scalars().all()
    for a in existing:
        if a.status != "pending":
            return a
        return a  # pending action already exists — reuse it

    proc = find_procedure(finding)
    adv = advisory_for(finding.url)
    steps = "\n".join(f"- {s}" for s in proc.steps)
    site_advisory_line = (
        f"Site advisory: {adv['category']} "
        f"(recommended={adv['recommended'] if adv['recommended'] is not None else 'unknown'}). "
        f"{adv['rationale']}\n"
    )
    instruction_text = (
        f"Official organization: {proc.organization}\n"
        f"Procedure URL: {proc.procedure_url or 'not on file (verify manually)'}\n"
        f"{site_advisory_line}"
        f"Steps:\n{steps}\n\nRequest draft:\n{prepare_request(finding, proc)}"
    )
    action = m.PrivacyAction(
        finding_id=finding.id,
        recommended_action=f"Request removal of exposure '{finding.title}' from {proc.organization}",
        deletion_url=proc.procedure_url,
        instructions=instruction_text,
        evidence_reference=f"#{finding.id}",
        approval_required=True,
        status="pending",
    )
    db.add(action)
    return action


def research_scan(db, scan_id: int) -> dict[str, int]:
    """Research all candidate findings of a scan; idempotent. Returns counts."""
    findings = db.execute(
        select(m.Finding).where(m.Finding.scan_id == scan_id)
    ).scalars().all()
    created = 0
    skipped = 0
    for f in findings:
        if not is_candidate(f):
            continue
        before = db.execute(
            select(m.PrivacyAction).where(m.PrivacyAction.finding_id == f.id)
        ).scalar_one_or_none()
        if before is not None:
            skipped += 1
            continue
        research_finding(db, f)
        created += 1
    db.flush()
    return {"researchable": len(findings), "created": created, "skipped": skipped}


def _transition(db, action_id: int, to_status: str, actor: str, detail: str) -> m.PrivacyAction | None:
    action = db.get(m.PrivacyAction, action_id)
    if action is None:
        return None
    if action.status != "pending":
        return action  # only pending can transition
    action.status = to_status
    if to_status == "approved":
        action.approved_at = _utcnow()
    db.add(m.AuditLog(actor=actor, action="approve" if to_status == "approved" else "update",
                      entity_type="action", entity_id=action.id, detail=detail))
    return action


def approve_action(db, action_id: int, actor: str = "user") -> m.PrivacyAction | None:
    """Human approval gate — approval never triggers sending anything."""
    return _transition(db, action_id, "approved", actor,
                       "deletion request approved by human — sending remains a separate manual step")


def decline_action(db, action_id: int, actor: str = "user") -> m.PrivacyAction | None:
    return _transition(db, action_id, "declined", actor, "deletion request declined by human")