"""File-upload hardening: size cap, magic bytes, decompression bombs (Phase 13)."""

import io
import struct
import zlib

from PIL import Image as PILImage


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (16, 16), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _core_png() -> bytes:
    return _png_bytes()


def _pixel_bomb_png(width: int, height: int) -> bytes:
    """Take a tiny valid PNG and rewrite its IHDR to fake huge dimensions."""
    data = bytearray(_core_png())
    # PNG layout: 8-byte signature, then IHDR chunk (length 4, type 4, data 13, crc 4).
    assert data[12:16] == b"IHDR"
    struct.pack_into(">I", data, 16, width)
    struct.pack_into(">I", data, 20, height)
    crc = zlib.crc32(data[12:29]) & 0xFFFFFFFF
    struct.pack_into(">I", data, 29, crc)
    return bytes(data)


def test_upload_rejects_oversize(client):
    scan_id = _create(client)
    big = b"\x89PNG\r\n\x1a\n" + b"x" * 200_000
    r = client.post(f"/api/scans/{scan_id}/image", files={"file": ("big.png", big, "image/png")})
    assert r.status_code == 413


def test_upload_rejects_garbage_bytes(client):
    scan_id = _create(client)
    r = client.post(f"/api/scans/{scan_id}/image", files={"file": ("x.png", b"not-png", "image/png")})
    assert r.status_code == 422


def test_upload_rejects_decompression_bomb(client):
    payload = _pixel_bomb_png(60_000, 60_000)
    assert len(payload) < 5_000  # tiny on disk: the guard is on declared pixels
    scan_id = _create(client)
    r = client.post(f"/api/scans/{scan_id}/image", files={"file": ("bomb.png", payload, "image/png")})
    assert r.status_code == 422


def test_upload_accepts_small_valid_image(client):
    scan_id = _create(client)
    r = client.post(f"/api/scans/{scan_id}/image", files={"file": ("ok.png", _png_bytes(), "image/png")})
    assert r.status_code == 201


def _create(client) -> int:
    r = client.post("/api/scans", json={"targetType": "image", "targetValue": "p.png"})
    assert r.status_code == 201
    return r.json()["id"]