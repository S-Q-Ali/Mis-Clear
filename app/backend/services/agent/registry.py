"""Agent tool registry (SPEC-agent-tools).

Wraps the existing deterministic adapters behind a strict-JSON contract the
ReAct loop (agent-core) can call. Tools are read-only and allowlisted: shell
execution and URL following never exist here, and web/model content is always
treated as untrusted data by consumers.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.backend.services.agent.breach import BreachChecker
from tools.base import EVIDENCE_MAX_CHARS, ToolAdapter, ToolFinding, ToolResult
from tools.photo.nsfw import NsfwAdapter
from tools.photo.reverse_search import ReverseImageSearchAdapter
from tools.photo.vision import VisionAdapter
from tools.registry import MANIFEST_DIR, build_registry
from tools.sitecheck import SiteCheckAdapter, load_manifest
from tools.web.dns import DnsAdapter
from tools.web.github import GithubAdapter
from tools.web.search import SearchAdapter
from tools.web.whois import WhoisAdapter

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
_USERNAME_RE = re.compile(
    r"(?:github\.com/|x\.com/|twitter\.com/|instagram\.com/|reddit\.com/user/)([\w-]+)",
    re.IGNORECASE,
)
GRAPH_EXPAND_MAX = 25


@dataclass(frozen=True)
class ToolSpec:
    """One agent-callable tool."""

    name: str
    description: str
    args: dict[str, Any]
    runner: Callable[..., dict]


def finding_to_json(f: ToolFinding) -> dict[str, Any]:
    return {
        "type": f.type,
        "title": f.title,
        "source": f.source,
        "url": f.url,
        "evidence": f.evidence[:EVIDENCE_MAX_CHARS] if f.evidence else None,
        "confidence": f.confidence,
        "severity": f.severity,
        "scope": f.scope,
    }


def result_to_json(result: ToolResult) -> dict[str, Any]:
    note = result.coverage.get("note") if isinstance(result.coverage, dict) else None
    if not note and result.errors:
        note = result.errors[0]
    return {
        "ok": result.status == "completed",
        "status": result.status,
        "note": note or "",
        "findings": [finding_to_json(f) for f in result.findings],
        "errors": list(result.errors),
    }


def adapter_tool(name: str, description: str, args: dict, adapter: ToolAdapter) -> ToolSpec:
    def run(**kwargs: Any) -> dict:
        return result_to_json(adapter.run(str(kwargs.get("target", ""))))

    return ToolSpec(name=name, description=description, args=args, runner=run)


def _str_arg(description: str) -> dict[str, Any]:
    return {"type": "string", "description": description, "required": True}


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return str(value)


def _extract_candidates(sources: list[str]) -> dict[str, list[str]]:
    joined = "\n".join(sources)
    emails = sorted({m.group(0).lower() for m in _EMAIL_RE.finditer(joined)})
    usernames = sorted({m.group(1).lower() for m in _USERNAME_RE.finditer(joined)})
    return {
        "emails": emails[:GRAPH_EXPAND_MAX],
        "usernames": usernames[:GRAPH_EXPAND_MAX],
    }


def build_agent_tools(
    *,
    manifest_email: str | Path | None = None,
    manifest_username: str | Path | None = None,
    timeout: float = 10.0,
    client_factory: Callable[[], httpx.Client | None] | None = None,
    router: Any = None,
    strict_local: bool = True,
    hybrid_allowed: bool = False,
    site_manifest: str | Path | None = None,
    breach_base_url: str | None = None,
    breach_checker: Any = None,
) -> dict[str, ToolSpec]:
    """Return the allowlisted {name: ToolSpec} set for the agent loop."""

    make = client_factory or (lambda: None)

    def client() -> httpx.Client | None:
        return make()

    tools: dict[str, ToolSpec] = {}

    adapter_by_name: dict[str, ToolAdapter] = {
        a.name: a
        for a in build_registry(
            manifest_email=manifest_email,
            manifest_username=manifest_username,
            timeout=timeout,
            client_factory=client_factory,
        )
    }

    tools["dns"] = adapter_tool(
        "dns",
        "Resolve DNS records for a domain (A/AAAA/MX/TXT...). Read-only.",
        {"target": _str_arg("domain to resolve")},
        adapter_by_name[DnsAdapter.name],
    )
    tools["whois"] = adapter_tool(
        "whois",
        "Fetch WHOIS registration data for a domain. Read-only.",
        {"target": _str_arg("domain to look up")},
        adapter_by_name[WhoisAdapter.name],
    )
    tools["web_search"] = adapter_tool(
        "web_search",
        "Public web search: returns result links + short snippets. Weak evidence only.",
        {"target": _str_arg("search query")},
        adapter_by_name[SearchAdapter.name],
    )
    tools["github_user"] = adapter_tool(
        "github_user",
        "Check whether a value exists as a GitHub user/email. Read-only.",
        {"target": _str_arg("email or username")},
        adapter_by_name[GithubAdapter.name],
    )
    tools["email_lookup"] = adapter_tool(
        "email_lookup",
        "Check an email address across many sign-up sites (manifest catalog).",
        {"target": _str_arg("email address")},
        adapter_by_name["holehe"],
    )
    tools["username_lookup"] = adapter_tool(
        "username_lookup",
        "Check a username across many platforms (manifest catalog).",
        {"target": _str_arg("username")},
        adapter_by_name["sherlock"],
    )

    def run_site_check(**kwargs: Any) -> dict:
        mode = str(kwargs.get("mode") or "email").lower()
        if mode not in ("email", "username"):
            return {"ok": False, "note": f"unknown site-check mode: {mode!r}"}
        manifest_path = Path(site_manifest) if site_manifest else MANIFEST_DIR / f"{mode}.json"
        sites = load_manifest(manifest_path)
        if not sites:
            return {"ok": False, "note": f"no site manifest for mode {mode}"}
        adapter = SiteCheckAdapter(
            tool="site-check",
            target_type=mode,
            manifest=sites,
            client=client(),
            timeout=timeout,
        )
        return result_to_json(adapter.run(str(kwargs.get("target", ""))))

    tools["site_check"] = ToolSpec(
        name="site_check",
        description="Probe one value against a site manifest (mode=email|username).",
        args={
            "target": _str_arg("email or username to probe"),
            "mode": {
                "type": "string",
                "description": "email or username",
                "required": True,
            },
        },
        runner=run_site_check,
    )

    tools["photo_vision"] = adapter_tool(
        "photo_vision",
        "Analyze an image file locally/hybrid: objects, text, no identities. ai-analysis.",
        {"target": _str_arg("absolute path to image file")},
        VisionAdapter(router=router, strict_local=strict_local),
    )
    tools["photo_nsfw"] = adapter_tool(
        "photo_nsfw",
        "Classify an image for NSFW content on the approved Colab worker (hybrid only).",
        {"target": _str_arg("absolute path to image file")},
        NsfwAdapter(router=router, strict_local=strict_local),
    )
    tools["photo_reverse_search"] = adapter_tool(
        "photo_reverse_search",
        "Reverse image search (Yandex). Sends the image to a third-party engine; "
        "hybrid/approved only. Weak evidence.",
        {"target": _str_arg("absolute path to image file")},
        ReverseImageSearchAdapter(client=client(), provider="yandex", allowed=hybrid_allowed),
    )

    def run_graph_expand(**kwargs: Any) -> dict:
        sources = kwargs.get("sources") or []
        if not isinstance(sources, list):
            return {"ok": False, "note": "sources must be a list", "emails": [], "usernames": []}
        candidates = _extract_candidates([str(s) for s in sources])
        if not candidates["emails"] and not candidates["usernames"]:
            return {"ok": False, "note": "no candidates found", "emails": [], "usernames": []}
        return {
            "ok": True,
            "note": (
                f"{len(candidates['emails'])} email, {len(candidates['usernames'])} "
                "username candidate(s)"
            ),
            **candidates,
        }

    tools["graph_expand"] = ToolSpec(
        name="graph_expand",
        description="Extract new email/username candidates from a set of evidence strings.",
        args={
            "sources": {
                "type": "list",
                "description": "URLs/evidence snippets to mine for candidates",
                "required": True,
            }
        },
        runner=run_graph_expand,
    )

    breaker = breach_checker or BreachChecker(base_url=breach_base_url, client=client() or None)

    def run_breach_check(**kwargs: Any) -> dict:
        passwords = kwargs.get("passwords") or []
        if not isinstance(passwords, list) or not passwords:
            return {
                "ok": False,
                "note": "passwords list required (ephemeral k-anonymity check)",
                "items": [],
                "checked": 0,
                "breached": 0,
            }
        return _json_safe(breaker.check_many([str(p) for p in passwords]))

    tools["breach_check"] = ToolSpec(
        name="breach_check",
        description=(
            "Check passwords against the public breach range API using k-anonymity. "
            "Inputs are ephemeral and never stored."
        ),
        args={
            "passwords": {
                "type": "list",
                "description": "passwords to check (never persisted)",
                "required": True,
            }
        },
        runner=run_breach_check,
    )

    return tools