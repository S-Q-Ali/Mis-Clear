"""Phase 6: OSINT adapter unit tests. All transports are faked — zero real network."""

import pytest
import httpx

from tools.base import ToolAdapter, ToolFinding, ToolResult
from tools.email.holehe import HoleheAdapter
from tools.sitecheck import SiteSpec, load_manifest
from tools.username.sherlock import SherlockAdapter
from tools.web.dns import DnsAdapter, _domain_of
from tools.web.github import GithubAdapter
from tools.web.search import SearchAdapter
from tools.web.whois import WhoisAdapter


def make_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


# ---------------- base contract ----------------

def test_finding_rejects_bad_confidence_and_severity():
    with pytest.raises(ValueError):
        ToolFinding(type="t", title="t", source="s", confidence="definitely")
    with pytest.raises(ValueError):
        ToolFinding(type="t", title="t", source="s", severity="panic")


def test_adapter_base_requires_contract():
    with pytest.raises(TypeError):
        ToolAdapter()


# ---------------- dns (DNS-over-HTTPS) ----------------

def _dns_handler(request: httpx.Request) -> httpx.Response:
    name = request.url.params.get("name")
    qtype = request.url.params.get("type")
    answers = {"A": [{"data": "93.184.216.34"}], "TXT": [{"data": 'v=spf1 -all'}]}.get(qtype, [])
    return httpx.Response(200, json={"Answer": answers})


def test_dns_returns_records_finding():
    a = DnsAdapter(client=make_client(_dns_handler))
    res = a.run("example.com")
    assert res.status == "completed"
    assert res.coverage["sources_checked"] >= 1
    assert len(res.findings) == 1
    assert res.findings[0].type == "domain_resolution"
    assert res.findings[0].confidence == "confirmed"
    assert res.findings[0].severity == "informational"


def test_dns_unresolvable_no_finding():
    a = DnsAdapter(client=make_client(lambda r: httpx.Response(200, json={"Answer": []})))
    res = a.run("nx.example.com")
    assert res.status == "completed"
    assert res.findings == []


def test_dns_http_error_failed():
    a = DnsAdapter(client=make_client(lambda r: httpx.Response(500)))
    res = a.run("example.com")
    assert res.status == "failed"
    assert res.errors


def test_dns_rejects_bad_target():
    a = DnsAdapter(client=make_client(lambda r: httpx.Response(200, json={})))
    res = a.run("not a domain")
    assert res.status == "failed"


def test_domain_of_handles_urls_and_emails():
    assert _domain_of("https://sub.example.com/path") == "sub.example.com"
    assert _domain_of("user@example.com") == "example.com"
    assert _domain_of("example.com") == "example.com"
    with pytest.raises(ValueError):
        _domain_of("!!!")


# ---------------- whois / RDAP ----------------

def _rdap_registration():
    return {
        "handle": "D123",
        "events": [{"eventAction": "registration", "eventDate": "2020-01-01T00:00:00Z"}],
        "entities": [{"roles": ["registrant"], "vcardArray": ["vcard", [["fn", {}, "text", "Alice"]]]}],
    }


def test_whois_registered_domain_confirmed():
    a = WhoisAdapter(client=make_client(lambda r: httpx.Response(200, json=_rdap_registration())))
    res = a.run("example.com")
    assert res.status == "completed"
    assert res.findings[0].type == "domain_registration"
    assert res.findings[0].confidence == "confirmed"
    assert "Alice" in res.findings[0].evidence


def test_whois_404_domain_not_registered_no_finding():
    a = WhoisAdapter(client=make_client(lambda r: httpx.Response(404)))
    res = a.run("nx-domain-test.invalid")
    assert res.status == "completed"
    assert res.findings == []
    assert "not found" in res.coverage["note"]


# ---------------- search (DDG HTML) ----------------

_DDG_HTML = """
<html><body>
<a class="result__url" href="https://example.test/p/alice">profile</a>
<div class="result__snippet">Alice's public profile.</div>
<a class="result__url" href="https://other.test/p/alice2">profile2</a>
<div class="result__snippet">Another hit for Alice.</div>
</body></html>
"""


def test_search_parses_hits_as_weak_evidence():
    a = SearchAdapter(client=make_client(lambda r: httpx.Response(200, text=_DDG_HTML)))
    res = a.run("alice")
    assert res.status == "completed"
    assert len(res.findings) == 2
    assert res.findings[0].confidence == "weak"
    assert res.findings[0].url == "https://example.test/p/alice"
    assert res.raw_reference
    assert res.coverage["note"].startswith("2")


def test_search_http_error_failed():
    a = SearchAdapter(client=make_client(lambda r: httpx.Response(503)))
    res = a.run("alice")
    assert res.status == "failed"


# ---------------- github ----------------

def test_github_username_found_confirmed():
    a = GithubAdapter(
        client=make_client(lambda r: httpx.Response(200, json={"login": "alice", "html_url": "https://github.com/alice", "name": "Alice", "public_repos": 3}))
    )
    res = a.run("alice")
    assert res.status == "completed"
    assert len(res.findings) == 1
    assert res.findings[0].type == "username_profile"
    assert res.findings[0].confidence == "confirmed"


def test_github_username_missing_no_finding():
    a = GithubAdapter(client=make_client(lambda r: httpx.Response(404)))
    res = a.run("no-such-user-xyz")
    assert res.status == "completed"
    assert res.findings == []
    assert "not found" in res.coverage["note"]


def test_github_email_search_finds_accounts():
    a = GithubAdapter(
        client=make_client(lambda r: httpx.Response(200, json={"total_count": 1, "items": [{"login": "alice", "html_url": "https://github.com/alice"}]}))
    )
    res = a.run("alice@example.com")
    assert res.findings[0].type == "email_account"
    assert res.findings[0].confidence == "probable"


# ---------------- site-check engine (holehe/sherlock) ----------------

_EMAIL_SITES = [
    SiteSpec({
        "name": "site-a", "mode": "email", "method": "POST",
        "probe_url": "https://a.test/check/{target}", "form_field": "email",
        "exists_marker": "is using this email", "missing_marker": "not registered",
    }),
    SiteSpec({
        "name": "site-b", "mode": "email", "method": "POST",
        "probe_url": "https://b.test/check", "form_field": "email",
        "exists_marker": "registered email", "missing_marker": "new to us",
    }),
]


def _email_handler(request: httpx.Request) -> httpx.Response:
    email = request.url.params.get("target", "") or ""
    if "a.test" in request.url.host:
        return httpx.Response(200, text="This email not registered")
    return httpx.Response(200, text="A registered email is happy")


def test_holehe_email_mode_finding_and_missing():
    a = HoleheAdapter(manifest=_EMAIL_SITES, client=make_client(_email_handler))
    res = a.run("alice@example.com")
    assert res.status == "completed"
    assert len(res.findings) == 1
    assert res.findings[0].source == "site-b"
    assert res.findings[0].confidence == "probable"
    assert res.coverage["sources_total"] == 2
    assert res.coverage["sources_checked"] == 2


_USER_SITES = [
    SiteSpec({
        "name": "profiles-x", "mode": "username", "method": "GET",
        "probe_url": "https://x.test/u/{target}", "exists_marker": "user-profile",
        "error_status_codes": [404],
    }),
]


def test_sherlock_username_mode_presence_and_absence():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("alice"):
            return httpx.Response(200, text="<div>user-profile</div>")
        return httpx.Response(404, text="not found")
    a = SherlockAdapter(manifest=_USER_SITES, client=make_client(handler))
    res = a.run("alice")
    assert len(res.findings) == 1 and res.findings[0].confidence == "probable"
    res2 = a.run("nobody")
    assert res2.findings == []


def test_load_manifest_sample_parses(tmp_path):
    path = tmp_path / "m.json"
    path.write_text('{"sites": [{"name": "n", "mode": "email", "probe_url": "https://x/{target}"}]}', encoding="utf-8")
    specs = load_manifest(path)
    assert specs and specs[0].name == "n"


# ---------------- registry ----------------

def _fake_client_factory():
    return make_client(lambda r: httpx.Response(200, json={}))


def test_registry_builds_default_set(tmp_path):
    import json as _json
    em = tmp_path / "email.json"
    um = tmp_path / "username.json"
    em.write_text(_json.dumps({"sites": [{"name": "e1", "mode": "email", "probe_url": "https://e/{target}"}]}))
    um.write_text(_json.dumps({"sites": [{"name": "u1", "mode": "username", "probe_url": "https://u/{target}"}]}))
    from tools.registry import build_registry, adapters_for
    reg = build_registry(manifest_email=em, manifest_username=um, client_factory=_fake_client_factory)
    names = {a.name for a in reg}
    assert {"dns", "whois", "search", "github", "holehe", "sherlock"} <= names
    email_tools = adapters_for("email", reg)
    assert {a.name for a in email_tools} == {"holehe", "github", "search"}
    user_tools = adapters_for("username", reg)
    assert {"sherlock", "github", "search"} <= {a.name for a in user_tools}
    assert "dns" in {a.name for a in adapters_for("custom", reg)}


def test_registry_without_manifests_skips_site_adapters(tmp_path):
    import json as _json
    missing = tmp_path / "none.json"
    missing.write_text(_json.dumps({"sites": []}))
    from tools.registry import build_registry
    reg = build_registry(manifest_email=missing, manifest_username=missing, client_factory=_fake_client_factory)
    assert "holehe" not in {a.name for a in reg}
    assert "sherlock" not in {a.name for a in reg}