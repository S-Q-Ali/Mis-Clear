"""Command-injection + dynamic guard tests (Phase 13)."""

import re
import subprocess
from pathlib import Path

import pytest


class FakeWhich:
    def __init__(self, path):
        self._path = path

    def __call__(self, cmd, *a, **kw):
        return self._path if cmd == self._path else None


def test_probe_nvidia_smi_uses_fixed_list(monkeypatch):
    from colab.capabilities import probe_nvidia_smi

    calls = []

    def fake_run(args, *, capture_output=False, text=False, timeout=None, check=False):
        calls.append({"args": args, "kwargs": {k: v for k, v in [("capture_output", capture_output), ("text", text), ("timeout", timeout)] if v}})
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="NVIDIA GeForce MX250\n1 MiB\n", stderr=b"")

    monkeypatch.setattr("shutil.which", lambda p: p)
    monkeypatch.setattr("subprocess.run", fake_run)
    probe_nvidia_smi("nvidia-smi")
    assert len(calls) == 1
    assert calls[0]["args"] == ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"]
    assert "shell" not in calls[0]["kwargs"]


def test_no_shell_in_subprocess_calls():
    src_dirs = [Path("app"), Path("tools"), Path("colab")]
    for d in src_dirs:
        if not d.exists():
            continue
        for py in d.rglob("*.py"):
            text = py.read_text(encoding="utf-8", errors="ignore")
            if "shell=True" in text and "# noqa" not in text.split("shell=True")[0].split("\n")[-1]:
                pytest.fail(f"shell=True found in {py}")


def test_no_eval_exec_os_system_in_app_tools_colab():
    dangerous = [re.compile(r"\beval\s*\("), re.compile(r"\bexec\s*\("), re.compile(r"\bos\.system\s*\(")]
    src_dirs = [Path("app"), Path("tools"), Path("colab")]
    for d in src_dirs:
        if not d.exists():
            continue
        for py in d.rglob("*.py"):
            text = py.read_text(encoding="utf-8", errors="ignore")
            for pat in dangerous:
                for m in pat.finditer(text):
                    start = max(0, m.start() - 40)
                    ctx = text[start : m.end() + 20].replace("\n", " ")
                    pytest.fail(f"dangerous call {m.group()!r} in {py}: ...{ctx}...")
