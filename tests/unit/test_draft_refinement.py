"""Slice 5: DRAFT refinement — wording only, deterministic URL guard.

Contract (no fabrication):
  - no backend            -> source DRAFT returned verbatim, refined=False
  - empty model output    -> source DRAFT returned verbatim
  - model rewrites        -> wording may change, URLs from source stay
  - invented URL          -> replaced "(removed by safety check)", url_sanitized=True
"""

import json

import httpx

from app.backend.services.draft_refinement import (
    Refinement,
    extract_urls,
    guard_urls,
    make_laptop_refiner,
    refine_draft,
)


def test_extract_urls_strips_punctuation():
    urls = extract_urls("see https://spokeo.com/optout, and https://a.test/x).")
    assert "https://spokeo.com/optout" in urls
    assert "https://a.test/x" in urls
    assert "https://a.test/x)" not in urls


def test_guard_urls_keeps_source_and_extra():
    source = "Visit https://spokeo.com/optout to proceed."
    out, changed = guard_urls(source + " plus https://truthfinder.com/opt-out/",
                              source, extra_allowed=["https://truthfinder.com/opt-out/"])
    assert changed is False
    assert "https://spokeo.com/optout" in out
    assert "https://truthfinder.com/opt-out/" in out


def test_guard_urls_removes_invented_url():
    source = "No link here."
    out, changed = guard_urls("Step 1: go to https://evil-remove-service.example/x", source)
    assert changed is True
    assert "evil-remove-service.example" not in out
    assert "(removed by safety check)" in out


def test_guard_urls_empty_source_drops_all():
    out, changed = guard_urls("See https://spokeo.com/optout", "", extra_allowed=[])
    assert changed is True
    assert "spokeo.com" not in out


def test_refine_draft_without_backend_verbatim():
    r = refine_draft("DRAFT abc")
    assert r == Refinement(text="DRAFT abc", refined=False, urls_sanitized=False,
                           note="no AI backend available; keeping source DRAFT verbatim",
                           backend="")
    assert r.text == "DRAFT abc"


def test_refine_draft_empty_output_verbatim():
    r = refine_draft("DRAFT abc", generate=lambda p: "   ", backend="fake")
    assert r.refined is False
    assert r.text == "DRAFT abc"


def test_refine_draft_keeps_good_wording_cleans_bad_url():
    source = ("Request via https://spokeo.com/optout. "
              "Remove my listing, reference #42.")
    good = ("Please remove my listing via the official form "
            "https://spokeo.com/optout (reference #42).")
    r = refine_draft(source, generate=lambda p: good, backend="qwen3:8b")
    assert r.refined is True
    assert r.urls_sanitized is False
    assert "spokeo.com/optout" in r.text
    assert r.backend == "qwen3:8b"


def test_refine_draft_sanitizes_invented_url():
    source = "Remove my listing, reference #42."
    bad = ("Remove my listing (reference #42). Fast removal guaranteed at "
           "https://pay-us-to-delete.example/x.")
    r = refine_draft(source, generate=lambda p: bad, backend="qwen3:8b")
    assert r.refined is True
    assert r.urls_sanitized is True
    assert "pay-us-to-delete.example" not in r.text
    assert r.text.count("(removed by safety check)") >= 1
    assert "reference #42" in r.text


def test_make_laptop_refiner_offline_returns_none(monkeypatch):
    import sys
    import types


    fake_router = types.SimpleNamespace()
    fake_router.route = lambda strict_local=True: None
    fake_mod = types.SimpleNamespace(router=fake_router, ModelUnavailableError=RuntimeError)
    monkeypatch.setitem(sys.modules, "app.backend.services.model_router", fake_mod)
    assert make_laptop_refiner() is None


# ---------------- worker-side removal_draft handler ----------------

def _fake_ollama_client(text: str) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        return httpx.Response(200, json={"response": text, "model": body["model"]})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_worker_removal_draft_returns_refined_text():
    from colab.capabilities import CapabilityReport
    from colab.handlers import get_handler

    client = _fake_ollama_client("Please remove my listing via the official form.")
    cap = CapabilityReport(gpu=True, models=["qwen3:8b"])
    out = get_handler("removal_draft")(
        {"text": "Remove my listing, reference #42.", "model": "qwen3:8b"}, cap, client=client)
    assert out["ok"] is True
    assert "official form" in out["text"]


def test_worker_removal_draft_rejects_empty():
    from colab.capabilities import CapabilityReport
    from colab.handlers import get_handler

    out = get_handler("removal_draft")({"text": "   "}, CapabilityReport(gpu=True, models=[]))
    assert out["ok"] is False
    assert "empty draft" in out["note"]