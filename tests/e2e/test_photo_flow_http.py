"""Phase 14 E2E: photo journey over real HTTP — real pipeline, no AI backend.

Uploads a synthetic PNG over multipart; the real photo pipeline runs; vision is
blocked (no backend) exactly as in production on a laptop without Ollama.
"""

from __future__ import annotations

import io

from PIL import Image as PILImage


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (32, 24), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def test_photo_journey_http(http):
    client, _ = http

    r = client.post("/api/scans", json={"targetType": "image", "targetValue": "photo.png"})
    assert r.status_code == 201
    scan_id = r.json()["id"]

    upload = client.post(
        f"/api/scans/{scan_id}/image",
        files={"file": ("photo.png", _png_bytes(), "image/png")},
    )
    assert upload.status_code == 201
    body = upload.json()
    assert body["status"] == "completed"
    assert body["coverage"]["findings"] == 2  # hash + phash (exif/qr absent, vision blocked)

    img = client.get(f"/api/scans/{scan_id}/image").json()
    assert img["filename"] == "photo.png"
    assert len(img["sha256"]) == 64
    assert len(img["md5"]) == 32

    graph = client.get(f"/api/scans/{scan_id}/graph").json()
    assert graph["nodes"] and graph["edges"]

    tool_runs = client.get(f"/api/scans/{scan_id}/tool-runs").json()
    tools = {t["tool"] for t in tool_runs["data"]}
    assert tools == {
        "photo-hash", "photo-phash", "photo-exif", "photo-qr", "photo-vision", "photo-nsfw",
    }
    vision = next(t for t in tool_runs["data"] if t["tool"] == "photo-vision")
    assert vision["status"] == "blocked"
    nsfw = next(t for t in tool_runs["data"] if t["tool"] == "photo-nsfw")
    assert nsfw["status"] == "blocked"  # NSFW classification is hybrid-only


def test_photo_upload_rejects_garbage_over_http(http):
    client, _ = http
    r = client.post("/api/scans", json={"targetType": "image", "targetValue": "bad.png"})
    scan_id = r.json()["id"]
    upload = client.post(
        f"/api/scans/{scan_id}/image",
        files={"file": ("bad.png", b"not-an-image-at-all", "image/png")},
    )
    assert upload.status_code == 422