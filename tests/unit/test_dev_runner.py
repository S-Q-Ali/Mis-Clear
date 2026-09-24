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


def test_frontend_url_points_at_vite(dev):
    assert dev.frontend_url() == "http://127.0.0.1:5173"


def test_colab_notebook_url_is_open_in_colab_link(dev):
    url = dev.colab_notebook_url()

    assert url.startswith("https://colab.research.google.com/github/")
    assert url.endswith("/blob/main/colab/privacy_guardian_worker.ipynb")


def test_open_in_browser_calls_webbrowser(dev, monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr(dev.webbrowser, "open", lambda url: opened.append(url) or True)

    assert dev.open_in_browser("http://example.test") is True
    assert opened == ["http://example.test"]


def test_copy_to_clipboard_uses_clip_on_windows(dev, monkeypatch):
    calls: list[tuple] = []

    class _Done:
        returncode = 0

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return _Done()

    monkeypatch.setattr(dev.sys, "platform", "win32")
    monkeypatch.setattr(dev.subprocess, "run", fake_run)

    assert dev.copy_to_clipboard("https://x.trycloudflare.com") is True
    assert calls[0][0] == ["clip"]
    assert calls[0][1]["input"] == "https://x.trycloudflare.com"


def test_copy_to_clipboard_returns_false_on_failure(dev, monkeypatch):
    monkeypatch.setattr(dev.sys, "platform", "win32")

    def boom(*args, **kwargs):
        raise FileNotFoundError("clip missing")

    monkeypatch.setattr(dev.subprocess, "run", boom)

    assert dev.copy_to_clipboard("x") is False


def test_wait_for_http_false_for_dead_port(dev):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        dead_port = probe.getsockname()[1]

    assert dev.wait_for_http(f"http://127.0.0.1:{dead_port}/health", timeout=0.5) is False
