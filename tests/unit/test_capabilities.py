"""Phase 8: worker capability probe tests (synthetic, no real GPU/network)."""

from __future__ import annotations

import json

import pytest

from colab.capabilities import (
    CapabilityReport,
    detect_capabilities,
    load_capabilities_from_json,
    probe_nvidia_smi,
)


# ---------- nvidia-smi probe ----------

def test_probe_nvidia_smi_missing_binary(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _cmd: None)
    assert probe_nvidia_smi("definitely-not-a-real-gpu-tool") is None


def test_probe_nvidia_smi_parses_csv(tmp_path, monkeypatch):
    fake = tmp_path / "fake-smi"
    fake.write_text("", encoding="utf-8")
    monkeypatch.setattr("shutil.which", lambda _cmd: str(fake))

    def fake_run(argv, **kwargs):  # noqa: ARG001
        class R:
            returncode = 0
            stdout = "T4 GPU, 16384 MiB\nGTX 1660, 6144 MiB\n"
        return R()

    monkeypatch.setattr("subprocess.run", fake_run)
    info = probe_nvidia_smi("fake-smi")
    assert info is not None
    assert info["gpu"] is True
    assert info["gpus"] == ["T4 GPU", "GTX 1660"]
    assert info["gpu_count"] == 2
    assert info["vram_mb"] == 16384


def test_probe_nvidia_smi_nonzero_return(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _cmd: "fake-smi")

    def fake_run(argv, **kwargs):  # noqa: ARG001
        class R:
            returncode = 1
            stdout = ""
        return R()

    monkeypatch.setattr("subprocess.run", fake_run)
    assert probe_nvidia_smi("fake-smi") is None


# ---------- full detection ----------

def test_detect_capabilities_cpu_fallback_without_gpu(monkeypatch):
    monkeypatch.setattr("colab.capabilities.probe_nvidia_smi", lambda _path: None)
    monkeypatch.setattr("colab.capabilities.ollama_tags", lambda _url: [])

    report = detect_capabilities(probe_gpu=True)
    assert report.gpu is False
    assert report.gpu_count == 0
    assert report.cpu is True
    assert report.models == []


def test_detect_capabilities_with_gpu_and_models(monkeypatch):
    monkeypatch.setattr(
        "colab.capabilities.probe_nvidia_smi",
        lambda _path: {"gpu": True, "gpus": ["T4"], "gpu_count": 1, "vram_mb": 15360},
    )
    monkeypatch.setattr("colab.capabilities.ollama_tags", lambda _url: ["qwen3:8b", "gemma3:4b"])

    report = detect_capabilities()
    assert report.gpu is True
    assert report.gpus == ["T4"]
    assert report.vidMemory == 15360
    assert report.models == ["qwen3:8b", "gemma3:4b"]
    adv = report.advertise()
    assert adv["gpu"] is True and adv["vram_mb"] == 15360


# ---------- ad-hoc JSON loading ----------

def test_load_capabilities_from_json(tmp_path):
    path = tmp_path / "caps.json"
    path.write_text(json.dumps({
        "gpu": True, "gpus": ["T4"], "gpu_count": 1, "vram_mb": 15360,
        "cpu": True, "models": ["qwen3:8b"],
    }), encoding="utf-8")
    report = load_capabilities_from_json(path)
    assert report.gpu is True
    assert report.gpus == ["T4"]
    assert report.vidMemory == 15360
    assert report.models == ["qwen3:8b"]


def test_capability_report_defaults_safe():
    report = CapabilityReport()
    assert report.gpu is False
    assert report.cpu is True
    assert report.models == []
    assert report.advertise()["gpu"] is False