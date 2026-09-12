"""Worker capability advertisement (Phase 8).

Deterministic, side-effect free probe: GPU/CPU info + model availability.
GPU detection via `nvidia-smi` is optional (parse JSON); any failure on any
backend falls back to a safe, honest `{"gpu": false, "cpu": true, "models": []}`.

Never fabricates a GPU or model that is not actually present.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CapabilityReport:
    gpu: bool = False
    gpus: list[str] = field(default_factory=list)
    cpu: bool = True
    gpu_count: int = 0
    vidMemory: int = 0  # noqa: N815 - JSON-facing field
    models: list[str] = field(default_factory=list)

    def advertise(self) -> dict[str, Any]:
        return {
            "worker": "privacy-guardian",
            "gpu": self.gpu,
            "gpus": self.gpus,
            "gpu_count": self.gpu_count,
            "cpu": self.cpu,
            "vram_mb": self.vidMemory,
            "models": self.models,
        }


def probe_nvidia_smi(path: str = "nvidia-smi") -> dict[str, Any] | None:
    """Return nvidia-smi JSON ({gpus/...}) or None when unavailable/unparseable."""
    if shutil.which(path) is None:
        return None
    try:
        proc = subprocess.run(
            [path, "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode != 0:
            return None
        gpus: list[str] = []
        vram = 0
        for raw in proc.stdout.strip().splitlines():
            parts = [p.strip() for p in raw.split(",")]
            if not parts or not parts[0]:
                continue
            gpus.append(parts[0])
            try:
                vram = max(vram, int(parts[1].replace(" MiB", "")))
            except (ValueError, IndexError):
                pass
        if not gpus:
            return None
        return {"gpu": True, "gpus": gpus, "gpu_count": len(gpus), "vram_mb": vram}
    except (subprocess.SubprocessError, OSError):
        return None


def ollama_tags(base_url: str = "http://127.0.0.1:11434") -> list[str]:
    """List locally available Ollama models via /api/tags (best-effort)."""
    import httpx

    try:
        with httpx.Client(timeout=3) as client:
            resp = client.get(f"{base_url.rstrip('/')}/api/tags")
        resp.raise_for_status()
        models = (resp.json().get("models") or [])
        return [m.get("name") or "" for m in models if m.get("name")]
    except httpx.HTTPError:
        return []


def detect_capabilities(
    *,
    nvidia_smi_path: str = "nvidia-smi",
    ollama_url: str = "http://127.0.0.1:11434",
    probe_gpu: bool = True,
) -> CapabilityReport:
    report = CapabilityReport()
    if probe_gpu:
        gpu_info = probe_nvidia_smi(nvidia_smi_path)
        if gpu_info:
            report.gpu = True
            report.gpus = gpu_info["gpus"]
            report.gpu_count = gpu_info["gpu_count"]
            report.vidMemory = gpu_info["vram_mb"]
    report.models = ollama_tags(ollama_url)
    report.cpu = True
    return report


def load_capabilities_from_json(path: str | Path) -> CapabilityReport:
    """Load a previously saved report (test/offline replay)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return CapabilityReport(
        gpu=bool(data.get("gpu")),
        gpus=list(data.get("gpus") or []),
        cpu=bool(data.get("cpu", True)),
        gpu_count=int(data.get("gpu_count") or 0),
        vidMemory=int(data.get("vram_mb") or 0),
        models=list(data.get("models") or []),
    )