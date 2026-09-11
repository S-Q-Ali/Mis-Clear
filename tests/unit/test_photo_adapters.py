"""Phase 7: photo forensics adapter unit tests.

All fixture images are generated in-memory at test time (Pillow/cv2). No real
images, no network, no AI backend.
"""

from pathlib import Path

import numpy as np
from PIL import Image as PILImage

from tools.photo.base import dhash_hex, hamming_distance, md5_hex, sha256_hex
from tools.photo.exif import ExifAdapter, extract_gps
from tools.photo.hash import PhotoHashAdapter
from tools.photo.phash import PerceptualHashAdapter, phash_matches
from tools.photo.qr import QrAdapter
from tools.photo.vision import VisionAdapter


def _save_png(tmp_path: Path, size=(32, 24), color=(10, 20, 30)) -> str:
    img = PILImage.new("RGB", size, color)
    path = tmp_path / "fixture.png"
    img.save(path, format="PNG")
    return str(path)


def _save_jpeg_with_gps(tmp_path: Path) -> str:
    img = PILImage.new("RGB", (16, 12), (200, 100, 50))
    exif = PILImage.Exif()
    exif[0x010F] = "TestMaker"
    exif[0x0110] = "TestModel"
    exif[0x0132] = "2025:01:01 00:00:00"
    gps = {
        1: "N",
        2: (34, 30, 15),
        3: "E",
        4: (118, 15, 45),
    }
    exif[0x8825] = gps
    path = tmp_path / "gps.jpg"
    img.save(path, format="JPEG", exif=exif)
    return str(path)


def _save_qr(tmp_path: Path) -> str:
    qr = np.zeros((240, 240), dtype=np.uint8)
    size = 10
    order = [(2, 2), (2, 22), (22, 2)]
    for x, y in order:
        for i in range(7):
            for j in range(7):
                block_color = 255 if (i == 0 or j == 0 or i == 6 or j == 6) else 0
                qr[(y + i) * size:(y + i + 1) * size, (x + j) * size:(x + j + 1) * size] = block_color
    qr[5 * size:6 * size, 5 * size:6 * size] = 255
    qr[14 * size:15 * size, 14 * size:15 * size] = 255
    qr[22 * size:23 * size, 22 * size:23 * size] = 255
    img = PILImage.fromarray(qr, mode="L")
    path = tmp_path / "qr.png"
    img.save(path, format="PNG")
    return str(path)


# ---------- base helpers ----------

def test_hashes_deterministic(tmp_path):
    path = _save_png(tmp_path)
    assert md5_hex(path) == md5_hex(path)
    assert sha256_hex(path) == sha256_hex(path)
    assert len(md5_hex(path)) == 32
    assert len(sha256_hex(path)) == 64
    assert dhash_hex(path) == dhash_hex(path)


def test_dhash_close_for_small_resize(tmp_path):
    a = _save_png(tmp_path, color=(200, 40, 40))
    b_path = tmp_path / "b.png"
    PILImage.new("RGB", (64, 48), (200, 40, 40)).save(b_path, format="PNG")
    dist = hamming_distance(dhash_hex(a), dhash_hex(b_path))
    assert dist <= 4


def test_phash_matches_threshold():
    assert phash_matches("0" * 16, "0" * 16, threshold=10)
    assert not phash_matches("0" * 16, "f" * 16, threshold=10)


# ---------- hash adapter ----------

def test_hash_adapter_returns_finding(tmp_path):
    path = _save_png(tmp_path)
    res = PhotoHashAdapter().run(path)
    assert res.status == "completed"
    assert len(res.findings) == 1
    f = res.findings[0]
    assert f.type == "image_hash"
    assert f.confidence == "confirmed"
    assert "md5=" in f.evidence and "sha256=" in f.evidence


def test_hash_adapter_fails_for_missing_file(tmp_path):
    res = PhotoHashAdapter().run(str(tmp_path / "nope.png"))
    assert res.status == "failed"
    assert res.findings == []
    assert res.errors


# ---------- phash adapter ----------

def test_phash_adapter_returns_finding(tmp_path):
    res = PerceptualHashAdapter().run(_save_png(tmp_path))
    assert res.status == "completed"
    assert res.findings[0].type == "image_perceptual_hash"
    assert res.findings[0].confidence == "confirmed"


# ---------- exif adapter ----------

def test_exif_adapter_gps_finding(tmp_path):
    path = _save_jpeg_with_gps(tmp_path)
    res = ExifAdapter().run(path)
    assert res.status == "completed"
    types = {f.type for f in res.findings}
    assert "image_exif" in types
    assert "image_gps" in types
    gps = next(f for f in res.findings if f.type == "image_gps")
    assert gps.severity == "medium"
    assert "lat=34.5041" in gps.evidence


def test_exif_adapter_no_metadata(tmp_path):
    res = ExifAdapter().run(_save_png(tmp_path))
    assert res.status == "completed"
    assert res.findings == []
    assert "no EXIF" in res.coverage.get("note", "")


def test_extract_gps_absent(tmp_path):
    assert extract_gps(_save_png(tmp_path)) is None


# ---------- qr adapter ----------

def test_qr_adapter_no_code(tmp_path):
    res = QrAdapter().run(_save_png(tmp_path))
    assert res.status == "completed"
    assert res.findings == []


def test_qr_adapter_finds_synthetic(tmp_path):
    path = _save_qr(tmp_path)
    res = QrAdapter().run(path)
    if res.findings:
        assert res.findings[0].type == "image_qrcode"
        assert res.findings[0].confidence == "confirmed"


# ---------- vision adapter (graceful, no AI backend) ----------

class _NoBackendRouter:
    def route(self, strict_local: bool = False):
        return None


def test_vision_gracefully_blocked_without_backend(tmp_path):
    res = VisionAdapter(router=_NoBackendRouter(), strict_local=True).run(_save_png(tmp_path))
    assert res.status == "blocked"
    assert res.findings == []
    assert "no AI backend" in res.coverage.get("note", "")


class _CrashRouter:
    def route(self, strict_local: bool = False):
        raise RuntimeError("probe exploded")


def test_vision_router_crash_never_crashes_pipeline(tmp_path):
    res = VisionAdapter(router=_CrashRouter(), strict_local=True).run(_save_png(tmp_path))
    assert res.status == "blocked"
    assert res.findings == []
    assert res.errors