"""Phase 7: photo scan orchestrator + upload API (fake routers, no network)."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image as PILImage
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.backend import models as m
from app.backend.database.engine import init_db_at

# ---------- fake vision router (no AI backend) ----------

class _NoBackendRouter:
    def route(self, strict_local: bool = False):
        return None


def _png_bytes(color=(10, 20, 30)) -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (32, 24), color).save(buf, format="PNG")
    return buf.getvalue()


def test_orchestrator_image_scan_persists_image_row_and_findings(tmp_path):
    from app.backend.services.scan_orchestrator import run_scan
    from tools.photo.registry import photo_pipeline

    engine = init_db_at(str(tmp_path / "photo.db"))
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()

    img_path = tmp_path / "synthetic.png"
    img_path.write_bytes(_png_bytes())
    scan = m.Scan(target_type="image", target_value=str(img_path), scan_mode="local")
    session.add(scan)
    session.commit()

    adapters = photo_pipeline(router=_NoBackendRouter(), strict_local=True)
    run_scan(session, scan, registry=adapters)

    session.expire_all()
    scan = session.get(m.Scan, scan.id)
    assert scan.status == "completed"
    assert scan.coverage["tools_ran"] == 5
    assert scan.coverage["findings"] == 2  # hash=1 + phash=1; exif/qr absent in PNG, vision blocked

    image = session.execute(select(m.Image).where(m.Image.scan_id == scan.id)).scalars().first()
    assert image is not None
    assert image.filename == "synthetic.png"
    assert len(image.md5) == 32 and len(image.sha256) == 64
    assert image.phash is not None

    findings = session.execute(select(m.Finding).where(m.Finding.scan_id == scan.id)).scalars().all()
    types = {f.type for f in findings}
    assert "image_hash" in types and "image_perceptual_hash" in types

    runs = session.execute(select(m.ToolRun).where(m.ToolRun.scan_id == scan.id)).scalars().all()
    assert {r.tool for r in runs} == {"photo-hash", "photo-phash", "photo-exif", "photo-qr", "photo-vision"}
    vision = next(r for r in runs if r.tool == "photo-vision")
    assert vision.status == "blocked"


# ---------- upload API ----------

def _make_client(tmp_path, monkeypatch):
    import app.backend.api.scans as scn
    import app.backend.api.workers as wk
    import app.backend.config as cfg
    import app.backend.database.engine as eng

    test_settings = cfg.Settings(
        database_path=str(tmp_path / "api_photo.db"),
        upload_dir=str(tmp_path / "uploads"),
        ollama_url="",
        colab_ollama_url="",
    )
    monkeypatch.setattr(cfg, "settings", test_settings)
    monkeypatch.setattr(eng, "settings", test_settings)
    monkeypatch.setattr(wk, "settings", test_settings)
    monkeypatch.setattr(scn, "settings", test_settings)

    eng.engine = eng.build_engine(test_settings.database_path)
    eng.SessionLocal = sessionmaker(bind=eng.engine, autoflush=False, autocommit=False)
    eng.init_db()

    from app.backend.main import create_app

    return TestClient(create_app())


def test_upload_image_runs_photo_pipeline(client):
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
    assert body["coverage"]["findings"] == 2

    img = client.get(f"/api/scans/{scan_id}/image")
    assert img.status_code == 200
    d = img.json()
    assert d["filename"] == "photo.png"
    assert len(d["sha256"]) == 64

    tool_runs = client.get(f"/api/scans/{scan_id}/tool-runs")
    tools = {t["tool"] for t in tool_runs.json()["data"]}
    assert tools == {"photo-hash", "photo-phash", "photo-exif", "photo-qr", "photo-vision"}


def test_upload_rejects_garbage_bytes(client):
    r = client.post("/api/scans", json={"targetType": "image", "targetValue": "bad.png"})
    scan_id = r.json()["id"]
    upload = client.post(
        f"/api/scans/{scan_id}/image",
        files={"file": ("bad.png", b"not-an-image-at-all", "image/png")},
    )
    assert upload.status_code == 422


def test_upload_requires_image_target(client):
    r = client.post("/api/scans", json={"targetType": "email", "targetValue": "a@example.com"})
    scan_id = r.json()["id"]
    upload = client.post(
        f"/api/scans/{scan_id}/image",
        files={"file": ("x.png", _png_bytes(), "image/png")},
    )
    assert upload.status_code == 400


def test_upload_missing_scan(client):
    upload = client.post(
        "/api/scans/99999/image",
        files={"file": ("x.png", _png_bytes(), "image/png")},
    )
    assert upload.status_code == 404


@pytest.fixture()
def client(tmp_path, monkeypatch):
    yield _make_client(tmp_path, monkeypatch)