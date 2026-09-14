"""Category-aware removal procedures (Phase 16, slice 5) — deterministic.

Selects a procedure for one finding URL:

  1. curated removal registry (`removal.json`) wins — official URL + channel;
  2. else the curated category template (data-broker opt-out, adult/NCII
     takedown, forum/social/... flows);
  3. unknown domains stay HONEST: known=False, no invented URL.

`finding_type` steers the template only when nothing curated exists and the
finding is image/hosted-content (image_exposure / image_nsfw) — in that case the
adult takedown template is used because the finding itself proves sensitive
hosted content, not the domain's reputation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.backend.services.removal_registry import find_removal_record
from app.backend.services.site_advisory import _hostname_of, category_of

IMAGE_FINDING_TYPES = {"image_exposure", "image_nsfw"}

CATEGORY_TEMPLATES: dict[str, list[str]] = {
    "data-broker": [
        "Open the broker's official opt-out / suppression page.",
        "Submit an opt-out request for the exact record exposed.",
        "Keep a dated copy of the confirmation.",
        "Re-check the listing after the stated processing window.",
    ],
    "adult": [
        "Report the content through the platform's official content-takedown / safety flow.",
        "If an image is of you and was shared without consent, say so explicitly and reference the evidence.",
        "Keep a dated record of the report reference number.",
        "Re-verify the content is gone; a follow-up report may be needed.",
    ],
    "forum": [
        "Use the forum's official account-deletion / content-report flow.",
        "Describe the post/account precisely with a link to the evidence.",
        "Keep a dated copy of the confirmation.",
    ],
    "social": [
        "Use the platform's official account deletion flow.",
        "Follow the confirmation prompts and keep a dated record.",
    ],
    "professional": [
        "Use the platform's official account-closing / content-removal flow.",
        "Keep a dated copy of the confirmation.",
    ],
    "legit": [
        "Use the service's official account deletion flow.",
        "Keep a dated copy of the confirmation.",
    ],
    "dev": [
        "Use the platform's official account deletion flow.",
        "Keep a dated copy of the confirmation.",
    ],
    "commerce": [
        "Use the service's official account / content removal flow.",
        "Keep a dated copy of the confirmation.",
    ],
    "unknown": [
        "No curated procedure is on file for this domain.",
        "Verify the identity of the official service and locate its official support/safety page.",
        "Follow the official account-removal flow and keep a dated record.",
    ],
}


@dataclass
class RemovalProcedure:
    domain: str
    organization: str
    category: str
    removal_channel: str
    procedure_url: str | None
    steps: list[str]
    known: bool
    extra: dict[str, Any] = field(default_factory=dict)


def procedure_for_finding(
    url: str | None,
    finding_type: str = "email_exposure",
) -> RemovalProcedure:
    rec = find_removal_record(url)
    if rec is not None:
        category = rec.get("category") or "unknown"
        steps = CATEGORY_TEMPLATES.get(category) or CATEGORY_TEMPLATES["unknown"]
        return RemovalProcedure(
            domain=rec["domain"],
            organization=rec.get("organization") or rec["domain"],
            category=category,
            removal_channel=rec.get("removal_channel", "manual"),
            procedure_url=rec.get("removal_url"),
            steps=list(steps),
            known=True,
        )
    host = _hostname_of(url)
    if finding_type in IMAGE_FINDING_TYPES:
        category = "adult"
    else:
        category = category_of(url) or "unknown"
    steps = CATEGORY_TEMPLATES.get(category) or CATEGORY_TEMPLATES["unknown"]
    return RemovalProcedure(
        domain=(host or "unknown").lower(),
        organization=(host or "unknown").lower(),
        category=category,
        removal_channel="manual",
        procedure_url=None,
        steps=list(steps),
        known=False,
    )