"""EXIF + GPS metadata extraction adapter (Phase 7).

EXIF data is untrusted metadata: it is parsed and reported, never executed.
"""

from __future__ import annotations

import time
from typing import Any

from PIL import ExifTags

from tools.base import ToolAdapter, ToolFinding, ToolResult
from tools.photo.base import load_rgb

_GPS_TAG_KEYS = {k: v for v, k in ExifTags.GPSTAGS.items()}


def _normalize_exif_tags(raw: dict[int, Any]) -> dict[str, Any]:
    tag_names = {k: v for v, k in ExifTags.TAGS.items()}
    out: dict[str, Any] = {}
    for code, value in raw.items():
        name = tag_names.get(code, f"tag_{code}")
        out[name] = str(value) if not isinstance(value, (str, int, float, list)) else value
    return out


def _gps_decimal(values: list[Any]) -> float | None:
    try:
        d = float(values[0])
        m = float(values[1])
        s = float(values[2]) if len(values) > 2 else 0.0
        return d + m / 60.0 + s / 3600.0
    except (TypeError, ValueError, IndexError):
        return None


def extract_gps(path: str) -> dict[str, Any] | None:
    """Return GPS info (raw + decimal lat/lon) or None when absent/unparseable."""
    img = load_rgb(path)
    raw = img._getexif() or {}
    gps_raw = raw.get(ExifTags.Base.GPSInfo if hasattr(ExifTags.Base, "GPSInfo") else 0x8825)
    if gps_raw is None:
        gps_raw = raw.get(0x8825)
    if not gps_raw:
        return None
    info: dict[str, Any] = {}
    for code, value in gps_raw.items():
        name = _GPS_TAG_KEYS.get(code, f"gps_{code}")
        info[name] = str(value) if not isinstance(value, (str, int, float)) else value
    lat = _gps_decimal(gps_raw.get(2))
    lon = _gps_decimal(gps_raw.get(4))
    if lat is not None and lon is not None:
        if gps_raw.get(1) == "S":
            lat = -lat
        if gps_raw.get(3) == "W":
            lon = -lon
        info["latitude"] = lat
        info["longitude"] = lon
    return info


class ExifAdapter(ToolAdapter):
    name = "photo-exif"
    target_types = ("image",)

    def run(self, target: str) -> ToolResult:
        start = time.perf_counter()
        result = ToolResult(self.name)
        try:
            img = load_rgb(target)
            raw = img._getexif() or {}
        except (OSError, ValueError) as exc:
            result.status = "failed"
            result.errors.append(f"cannot read metadata: {exc}")
            result.coverage = {"sources_total": 1, "sources_checked": 0,
                               "sources_failed": 1, "note": "unreadable file"}
            return result
        meta = _normalize_exif_tags(raw)
        if not meta:
            result.status = "completed"
            result.coverage = {"sources_total": 1, "sources_checked": 1,
                               "sources_failed": 0, "note": "no EXIF present"}
            result.duration_ms = int((time.perf_counter() - start) * 1000)
            return result
        result.findings.append(ToolFinding(
            type="image_exif",
            title="EXIF metadata present",
            source=self.name,
            evidence=_format_exif(meta),
            confidence="confirmed",
            severity="informational",
        ))
        gps = extract_gps(target)
        if gps and "latitude" in gps and "longitude" in gps:
            result.findings.append(ToolFinding(
                type="image_gps",
                title="GPS coordinates embedded in EXIF",
                source=self.name,
                evidence=f"lat={gps['latitude']}, lon={gps['longitude']}\n"
                         f"raw={gps}",
                confidence="confirmed",
                severity="medium",
            ))
        result.status = "completed"
        result.coverage = {"sources_total": 1, "sources_checked": 1,
                           "sources_failed": 0, "note": "local file"}
        result.duration_ms = int((time.perf_counter() - start) * 1000)
        return result


def _format_exif(meta: dict[str, Any]) -> str:
    preview_keys = {"Make", "Model", "DateTime", "Software", "GPSInfo"}
    shown = {k: v for k, v in meta.items() if k in preview_keys}
    lines = [f"{k}={v}" for k, v in shown.items()]
    if not lines:
        lines = [f"{k}={v}" for k, v in list(meta.items())[:8]]
    return "\n".join(lines)