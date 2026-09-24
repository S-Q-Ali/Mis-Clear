"""Unit tests for the local dev runner (scripts/dev.py).

The runner is a script, not an installed package, so it is loaded from its
path. Only its pure helpers are tested here; the process-launching paths are
verified manually.
"""

import importlib.util
import socket
from pathlib import Path

import pytest

DEV_PATH = Path(__file__).resolve().parents[2] / "scripts" / "dev.py"


@pytest.fixture(scope="module")
def dev():
    spec = importlib.util.spec_from_file_location("dev_runner", DEV_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repo_root_points_at_project_root(dev):
    root = dev.repo_root()

    assert (root / "app" / "backend" / "main.py").is_file()
    assert (root / "tools").is_dir()
    assert (root / "pyproject.toml").is_file()


def test_parse_tunnel_url_extracts_trycloudflare_host(dev):
    output = (
        "2026-09-24 INF Requesting new quick Tunnel on trycloudflare.com...\n"
        "+------------------------------------------------------+\n"
        "|  https://constitution-chance-live-series.trycloudflare.com  |\n"
        "+------------------------------------------------------+\n"
    )

    assert (
        dev.parse_tunnel_url(output)
        == "https://constitution-chance-live-series.trycloudflare.com"
    )


def test_parse_tunnel_url_returns_none_when_absent(dev):
    assert dev.parse_tunnel_url("no url here yet\n") is None


def test_is_port_free_true_for_unused_port(dev):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]

    assert dev.is_port_free("127.0.0.1", free_port) is True


def test_is_port_free_false_when_port_is_bound(dev):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen(1)
        busy_port = holder.getsockname()[1]

        assert dev.is_port_free("127.0.0.1", busy_port) is False


def test_build_backend_command_targets_uvicorn_app(dev):
    cmd = dev.build_backend_command("127.0.0.1", 8000)

    assert "uvicorn" in cmd
    assert "app.backend.main:app" in cmd
    assert cmd[cmd.index("--host") + 1] == "127.0.0.1"
    assert cmd[cmd.index("--port") + 1] == "8000"


def test_build_frontend_command_runs_npm_dev(dev):
    assert dev.build_frontend_command() == ["npm", "run", "dev"]


def test_build_tunnel_command_points_at_backend(dev):
    cmd = dev.build_tunnel_command("127.0.0.1", 8000)

    assert "cloudflared" in cmd[0]
    assert "tunnel" in cmd
    assert "http://127.0.0.1:8000" in cmd


def test_backend_env_colab_only_disables_local_ollama(dev):
    assert dev.backend_env(colab_only=True) == {"PG_OLLAMA_URL": ""}


def test_backend_env_default_is_empty(dev):
    assert dev.backend_env(colab_only=False) == {}
