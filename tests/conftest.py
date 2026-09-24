"""Shared test fixtures.

Tests must be hermetic: they must never inherit a developer's local `.env`.
`Settings` (pydantic-settings, env_prefix `PG_`) reads `.env` automatically, so
any Colab endpoint configured there would leak into fixtures that don't override
it — making "unconfigured" tests hit a real tunnel. Env vars outrank `.env`, so
neutralizing the Colab endpoints here keeps every test deterministic.
"""

import pytest


@pytest.fixture(autouse=True)
def _hermetic_colab_env(monkeypatch):
    """Force Colab endpoints empty so tests never touch a developer's .env."""
    monkeypatch.setenv("PG_COLAB_JOB_DISPATCHER_URL", "")
    monkeypatch.setenv("PG_COLAB_OLLAMA_URL", "")
