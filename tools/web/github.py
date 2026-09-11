"""GitHub public search/identity adapter (unauthenticated API).

- username: `GET /users/{login}` → 200 means the profile exists (confirmed).
- email:    `GET /search/users?q="{email}" in:email` → accounts using the address.
Rate limits (403) are reported, not fatal. API JSON is untrusted."""

from __future__ import annotations

import time

import httpx

from tools.base import ToolAdapter, ToolFinding, ToolResult

API_BASE = "https://api.github.com"


class GithubAdapter(ToolAdapter):
    name = "github"
    target_types = ("username", "email")

    def __init__(self, client: httpx.Client | None = None, timeout: float = 10.0) -> None:
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=True)
        self.timeout = timeout

    def run(self, target: str) -> ToolResult:
        start = time.monotonic()
        result = ToolResult(tool=self.name, status="completed",
                            coverage={"sources_total": 1, "sources_checked": 0, "sources_failed": 0})
        is_email = "@" in target
        try:
            if is_email:
                resp = self.client.get(
                    f"{API_BASE}/search/users", params={"q": f'"{target}" in:email'}, timeout=self.timeout
                )
                resp.raise_for_status()
                data = resp.json()
                items = data.get("items", [])[:5]
                result.coverage["sources_checked"] = 1
                for item in items:
                    login = item.get("login", "?")
                    result.findings.append(
                        ToolFinding(
                            type="email_account",
                            title=f"GitHub account {login} uses this email",
                            source="github",
                            url=item.get("html_url") or f"{API_BASE}/users/{login}",
                            evidence=f"public search matched email; account {login}",
                            confidence="probable",
                            severity="medium",
                            scope="public-profile",
                        )
                    )
            else:
                resp = self.client.get(f"{API_BASE}/users/{target}", timeout=self.timeout)
                if resp.status_code == 404:
                    result.coverage["sources_checked"] = 1
                    result.coverage["note"] = "username not found on GitHub"
                else:
                    resp.raise_for_status()
                    user = resp.json()
                    result.coverage["sources_checked"] = 1
                    result.findings.append(
                        ToolFinding(
                            type="username_profile",
                            title=f"GitHub profile exists: {target}",
                            source="github",
                            url=user.get("html_url") or f"{API_BASE}/users/{target}",
                            evidence=f"public profile; name={user.get('name') or 'n/a'}; "
                                     f"public_repos={user.get('public_repos') or 0}",
                            confidence="confirmed",
                            severity="low",
                            scope="public-profile",
                        )
                    )
        except httpx.HTTPError as exc:
            result.status = "failed"
            result.errors = [str(exc)]
        result.duration_ms = int((time.monotonic() - start) * 1000)
        result.raw_reference = API_BASE
        return result