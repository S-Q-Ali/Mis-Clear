"""k-anonymity breach check (SPEC-self-data). Ephemeral by design.

Inputs are used only to derive a SHA-1 digest. A 5-hex prefix is sent to a
range API (e.g. Pwned Passwords); the remaining 35 hex chars are compared
locally against the returned suffix list. Neither the plaintext input nor the
full hash is ever persisted or emitted.
"""

from __future__ import annotations

import hashlib
import re

import httpx

_LINE_RE = re.compile(r"^([0-9A-Fa-f]{35}):([0-9]+)")


def sha1_hex(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest().upper()


def k_anonymity_prefix(full_hash: str) -> str:
    return full_hash[:5]


def count_breach_suffixes(full_hash: str, range_body: str) -> int:
    """Suffix-match one digest against a HIBP-style `suffix:count` range body."""
    suffix = full_hash[5:].upper()
    for line in range_body.splitlines():
        m = _LINE_RE.match(line.strip())
        if not m:
            continue
        if m.group(1).upper() == suffix:
            return int(m.group(2))
    return 0


class BreachChecker:
    def __init__(self, base_url: str | None, client: httpx.Client | None = None) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.client = client or httpx.Client(timeout=10.0)

    def check_many(self, passwords: list[str]) -> dict:
        if not self.base_url:
            return {"ok": False, "blocked": True, "note": "no breach API configured"}
        fetched: dict[str, str] = {}
        items: list[dict] = []
        breached = 0
        for p in passwords:
            digest = sha1_hex(p)
            prefix = k_anonymity_prefix(digest)
            if prefix not in fetched:
                try:
                    resp = self.client.get(f"{self.base_url}/{prefix}", timeout=10.0)
                except httpx.HTTPError as exc:
                    return {"ok": False, "note": str(exc), "items": []}
                if resp.status_code != 200:
                    return {
                        "ok": False,
                        "blocked": True,
                        "note": f"range API returned HTTP {resp.status_code}",
                    }
                fetched[prefix] = resp.text
            matches = count_breach_suffixes(digest, fetched[prefix])
            items.append(
                {
                    "password_sha1_prefix": prefix,
                    "suffix_matches": matches,
                    "breached": matches > 0,
                }
            )
            if matches > 0:
                breached += 1
        return {"ok": True, "checked": len(passwords), "breached": breached, "items": items}