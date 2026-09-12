"""Path-traversal + upload filename neutralization (Phase 13)."""

import io
from pathlib import Path

from PIL import Image as PILImage


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (16, 16), (100, 120, 140)).save(buf, format="PNG")
    return buf.getvalue()


def _create_image_scan(client) -> int:
    r = client.post("/api/scans", json={"targetType": "image", "targetValue": "photo.png"})
    assert r.status_code == 201
    return r.json()["id"]


def _new_files_under(base: Path, before: set[Path]) -> list[Path]:
    base.mkdir(parents=True, exist_ok=True)
    return [p for p in base.iterdir() if p not in before]


def test_upload_path_traversal_filename_neutralized(client, tmp_path):
    upload_base = (tmp_path / "uploads")
    scan_id = _create_image_scan(client)
    r = client.post(
        f"/api/scans/{scan_id}/image",
        files={"file": ("../../../../evil.png", _png_bytes(), "image/png")},
    )
    assert r.status_code == 201
    stored = _new_files_under(upload_base, set())
    assert len(stored) == 1
    assert stored[0].resolve().is_relative_to(upload_base.resolve())


def test_upload_url_encoded_slashes_do_not_escape(client, tmp_path):
    upload_base = (tmp_path / "uploads")
    scan_id = _create_image_scan(client)
    r = client.post(
        f"/api/scans/{scan_id}/image",
        files={"file": ("..%2F..%2F..%2Fescape.png", _png_bytes(), "image/png")},
    )
    assert r.status_code == 201
    stored = _new_files_under(upload_base, set())
    assert len(stored) == 1
    assert stored[0].resolve().is_relative_to(upload_base.resolve())


def test_windows_backslash_does_not_escape(client, tmp_path):
    upload_base = (tmp_path / "uploads")
    scan_id = _create_image_scan(client)
    r = client.post(
        f"/api/scans/{scan_id}/image",
        files={"file": (r"..\..\..\evil.png", _png_bytes(), "image/png")},
    )
    assert r.status_code == 201
    stored = _new_files_under(upload_base, set())
    assert len(stored) == 1
    assert stored[0].resolve().is_relative_to(upload_base.resolve())


def test_display_name_stripped_of_path_components(client):
    scan_id = _create_image_scan(client)
    r = client.post(
        f"/api/scans/{scan_id}/image",
        files={"file": (r"sub\dir\..\tricky.png", _png_bytes(), "image/png")},
    )
    assert r.status_code == 201
    img = client.get(f"/api/scans/{scan_id}/image").json()
    assert img["filename"] == "tricky.png"