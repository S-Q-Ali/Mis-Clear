"""AI-assisted DRAFT refinement (Phase 16, slice 5) — wording only, never facts.

`refine_draft` sends the deletion DRAFT to an available LLM backend (local or the
approved Colab worker) with instructions that forbid inventing URLs, steps, or
facts. Whatever the model returns, the laptop ALWAYS runs a deterministic
URL-integrity post-check (`guard_urls`) before storing:

  - every http(s) URL in the refined text must be present in the source DRAFT
    (or in the handed-in set of pristine URLs, e.g. the curated removal page);
  - any other URL is replaced with "(removed by safety check)" — a fabricated
    URL can never survive into the stored instruction text;
  - if no backend is reachable, `refine_draft` returns the source DRAFT
    unchanged (honest fallback — never a guessed rewrite).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

_URL_RE = re.compile(r"https?://[^\s\"'<>]+")


def extract_urls(text: str) -> set[str]:
    """Extract bare http(s) URLs, stripping trailing punctuation."""
    out: set[str] = set()
    for m in _URL_RE.findall(text or ""):
        url = m.rstrip(".,;:)]}>\"'")
        if len(url) > 7:
            out.add(url)
    return out


def guard_urls(
    refined: str,
    source: str,
    extra_allowed: Iterable[str] = (),
) -> tuple[str, bool]:
    """Deterministic post-check: allow only URLs present in source + extra_allowed.

    Returns (sanitized_text, changed_bool). Unrecognized URLs are replaced with
    "(removed by safety check)". Requires a source string; empty source drops
    every URL."""
    allowed = extract_urls(source) | set(extra_allowed or [])
    changed = False

    def _repl(m: re.Match) -> str:
        nonlocal changed
        url = m.group(0)
        if url in allowed:
            return url
        changed = True
        return "(removed by safety check)"

    return _URL_RE.sub(_repl, refined or ""), changed


@dataclass
class Refinement:
    text: str
    refined: bool
    urls_sanitized: bool
    note: str = field(default="")
    backend: str = field(default="")


_NO_BACKEND_NOTE = "no AI backend available; keeping source DRAFT verbatim"


def refine_draft(
    draft: str,
    *,
    extra_allowed_urls: Iterable[str] = (),
    generate: Callable[[str], str] | None = None,
    backend: str = "",
) -> Refinement:
    """Refine a DRAFT's wording only. If `generate` is None or raises when no
    backend exists, the source DRAFT is returned unchanged with a honest note."""
    if generate is None:
        return Refinement(text=draft, refined=False, urls_sanitized=False,
                          note=_NO_BACKEND_NOTE, backend="")
    try:
        output = generate(draft)
    except Exception as exc:  # noqa: BLE001 — honest fallback, never crash research
        return Refinement(text=draft, refined=False, urls_sanitized=False,
                          note=f"refinement failed ({exc}); keeping source DRAFT", backend=backend)
    output = (output or "").strip()
    if not output:
        return Refinement(text=draft, refined=False, urls_sanitized=False,
                          note="empty model output; keeping source DRAFT", backend=backend)
    text, urls_sanitized = guard_urls(output, draft, extra_allowed_urls)
    return Refinement(text=text, refined=True, urls_sanitized=urls_sanitized,
                      note="wording refined; no new URLs/facts added", backend=backend)


def make_laptop_refiner() -> Callable[[str], str] | None:
    """Adapt the ModelRouter's available text backend into a `generate` callable.
    Returns None when no local backend is available — honesty per the module
    contract. Dims while offline; Colab is never used without approval."""
    try:
        from app.backend.services import model_router

        backend = model_router.router.route(strict_local=True)
        if backend is None or not backend.available():
            return None
        return lambda prompt: backend.generate(prompt, system=None).text
    except Exception:  # noqa: BLE001 — offline/unconfigured is a valid state
        return None