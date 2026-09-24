"""Agent tool registry contract (SPEC-agent-tools).

Covers: strict-JSON serialization of ToolResult/findings, allowlisted tool set,
blocked/failed adapters never raise, graph_expand candidate extraction, and
k-anonymity breach prefix handling (no plaintext / no full hash ever emitted).
"""

from __future__ import annotations

import hashlib

import httpx

from app.backend.services.agent.breach import (
    BreachChecker,
    count_breach_suffixes,
    k_anonymity_prefix,
    sha1_hex,
)
from app.backend.services.agent.registry import build_agent_tools, finding_to_json

DDG_HTML = """
<html><body>
<div class="result"><a class="result__url" href="https://example.com/alice">a</a>
<a class="result__snippet"><b>profile</b></a></div>
<div class="result"><a class="result__url" href="https://open-source.example/alice">b</a>
<a class="result__snippet">leak board</a></div>
</body></html>
"""


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


# --- breach helpers -------------------------------------------------------


def test_sha1_hex_is_upper_40_chars():
    digest = sha1_hex("password")
    assert len(digest) == 40
    assert digest == hashlib.sha1(b"password").hexdigest().upper()


def test_k_anonymity_prefix_is_first_5_chars():
    digest = sha1_hex("password")
    assert k_anonymity_prefix(digest) == digest[:5]
    assert len(k_anonymity_prefix(digest)) == 5


def test_count_breach_suffixes_matches_hibp_range_lines():
    digest = sha1_hex("password")
    suffix = digest[5:]
    body = f"0000000:5\n{suffix}:142\nFFFFFFF:1\n"
    assert count_breach_suffixes(digest, body) == 142
    assert count_breach_suffixes(sha1_hex("not-in-range"), body) == 0


def test_breaker_ephemeral_no_api_is_blocked():
    checker = BreachChecker(base_url="")
    out = checker.check_many(["password"])
    assert out["ok"] is False
    assert out["blocked"] is True
    assert "password" not in str(out)


def test_breaker_k_anonymity_only_prefix_and_count_returned():
    digest = sha1_hex("correct horse battery staple")
    suffix = digest[5:]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=f"{suffix}:42\n")

    client = _client(handler)
    checker = BreachChecker(base_url="https://api.pwned/range", client=client)
    out = checker.check_many(["correct horse battery staple"])
    assert out["checked"] == 1
    assert out["breached"] == 1
    assert out["items"][0]["suffix_matches"] == 42
    assert out["items"][0]["breached"] is True
    serialized = str(out)
    assert "correct horse" not in serialized
    assert digest not in serialized


def test_breaker_unique_prefixes_fetched_separately():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        suffix = request.url.path.split("/")[-1]
        calls.append(suffix)
        return httpx.Response(200, text=f"{suffix}:7\n")

    p1 = "prefix-probe-one"
    p2 = "prefix-probe-two"
    probes = ["prefix-probe-three", "prefix-probe-four", "prefix-probe-five"]
    if k_anonymity_prefix(sha1_hex(p1)) == k_anonymity_prefix(sha1_hex(p2)):
        for cand in probes:
            if k_anonymity_prefix(sha1_hex(cand)) != k_anonymity_prefix(sha1_hex(p1)):
                p2 = cand
                break

    checker = BreachChecker(base_url="https://api.pwned/range", client=_client(handler))
    out = checker.check_many([p1, p2])
    assert out["checked"] == 2
    assert len(calls) == 2
    assert calls == sorted({k_anonymity_prefix(sha1_hex(p1)), k_anonymity_prefix(sha1_hex(p2))}, key=str)


# --- registry --------------------------------------------------------------


def test_build_agent_tools_allowlist_present():
    tools = build_agent_tools()
    required = {
        "email_lookup", "username_lookup", "web_search", "dns", "whois",
        "github_user", "site_check", "photo_vision", "photo_nsfw",
        "photo_reverse_search", "graph_expand", "breach_check",
    }
    assert required.issubset(tools.keys())


def test_build_agent_tools_spec_shape():
    spec = build_agent_tools()["web_search"]
    assert spec.name == "web_search"
    assert spec.description
    assert isinstance(spec.args, dict)
    assert "target" in spec.args


def test_finding_to_json_is_json_safe_and_truncates():
    from tools.base import ToolFinding

    f = ToolFinding(
        type="search_hit",
        title="hit",
        source="duckduckgo",
        url="https://example.com",
        evidence="x" * 5000,
        confidence="weak",
        severity="informational",
    )
    js = finding_to_json(f)
    assert js["evidence"] is None or len(js["evidence"]) <= 2000
    assert js["type"] == "search_hit"


def test_failing_adapter_returns_ok_false_json_no_raise():
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    tools = build_agent_tools(client_factory=lambda: _client(boom))
    out = tools["web_search"].runner(target="someone@example.com", limit=3)
    assert out["ok"] is False
    assert out["status"] == "failed"
    assert isinstance(out["findings"], list)
    assert out["errors"]


def test_data_tools_blocked_without_approval():
    tools = build_agent_tools(strict_local=True, hybrid_allowed=False)
    out = tools["photo_reverse_search"].runner(target="C:/nope.png")
    assert out["ok"] is False
    assert out["status"] == "blocked"
    assert "hybrid" in out["note"].lower() or out["errors"]


def test_hybrid_reverse_search_returns_weak_exposure_findings(tmp_path):
    img = tmp_path / "fake.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    serp = '<a class="serp-item__link" href="https://site.example/x.jpg">i</a>'
    serp += '<a class="serp-item__link" href="https://forum.example/a.png">i</a>'
    tools = build_agent_tools(
        hybrid_allowed=True,
        client_factory=lambda: _client(lambda req: httpx.Response(200, text=serp)),
    )
    out = tools["photo_reverse_search"].runner(target=str(img))
    assert out["ok"] is True
    assert len(out["findings"]) == 2
    for f in out["findings"]:
        assert f["type"] == "image_exposure"
        assert f["confidence"] == "weak"
        assert f["url"].startswith("https://")


def test_web_search_parses_links_to_findings():
    tools = build_agent_tools(client_factory=lambda: _client(lambda req: httpx.Response(200, text=DDG_HTML)))
    out = tools["web_search"].runner(target='"alice smith" email')
    assert out["ok"] is True
    assert len(out["findings"]) == 2
    assert out["findings"][0]["url"] == "https://example.com/alice"


def test_graph_expand_extracts_emails_and_usernames():
    tools = build_agent_tools()
    out = tools["graph_expand"].runner(
        sources=["contact: a.b_2@example.com", "github.com/alice", "https://x.com/bob", "noise @ not-email"]
    )
    assert out["ok"] is True
    assert "a.b_2@example.com" in out["emails"]
    assert "alice" in out["usernames"]
    assert "bob" in out["usernames"]
    assert len(out["emails"]) <= 25


def test_graph_expand_empty_sources_is_failed_json():
    tools = build_agent_tools()
    out = tools["graph_expand"].runner(sources=[])
    assert out["ok"] is False
    assert out["emails"] == []