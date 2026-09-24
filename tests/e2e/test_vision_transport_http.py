"""Phase 15 E2E: hybrid photo scan routes vision to the Colab worker protocol.

Real HTTP + real pipeline + real temp SQLite. A simulated Colab worker thread
polls `GET /api/jobs/next` and posts a completed `JobResult`. The photo scan's
`photo-vision` tool therefore completes with an `image_vision` finding sourced
from the worker's text — proving the laptop never fakes results and the worker
text finds its way back into the evidence graph.
"""

from __future__ import annotations

import io
import threading
import time

from PIL import Image as PILImage


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (32, 24), (60, 90, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _fake_worker(client, out: dict, stop: threading.Event, expected_jobs: int = 2) -> None:
    processed = 0
    idle = 0
    while not stop.is_set() and processed < expected_jobs:
        nxt = client.get("/api/jobs/next")
        if nxt.status_code == 200:
            body = nxt.json()
            out["job_id"] = body["job_id"]
            out["internal_id"] = body["_internal_id"]
            out["payload"] = body.get("payload", {})
            out["post_status"] = client.post(
                f"/api/jobs/{body['job_id']}/result",
                json={
                    "job_id": body["job_id"],
                    "status": "completed",
                    "result": {"ok": True, "text": "two people in a green park", "model": "gemma3:4b"},
                    "errors": [],
                    "data_deleted": True,
                },
            ).status_code
            processed += 1
            idle = 0
        elif nxt.status_code == 204:
            idle += 1
            if idle > 60:
                break
            time.sleep(0.05)
        else:
            stop.set()
            return
    out["processed"] = processed


def test_hybrid_photo_scan_reaches_colab_worker_and_produces_finding(http, monkeypatch):
    from tools.base import ToolResult
    from tools.photo import reverse_search as rs

    def _blocked_reverse(self, target):
        r = ToolResult(self.name)
        r.status = "blocked"
        r.coverage = {"sources_total": 1, "sources_checked": 0, "sources_failed": 1,
                      "note": "test stub — no external reverse-search call"}
        return r

    monkeypatch.setattr(rs.ReverseImageSearchAdapter, "run", _blocked_reverse)

    client, _ = http
    worker_out: dict = {}
    stop = threading.Event()
    thread = threading.Thread(target=_fake_worker, args=(client, worker_out, stop), daemon=True)
    thread.start()
    try:
        r = client.post("/api/scans", json={"targetType": "image", "targetValue": "hy.png", "scanMode": "hybrid"})
        assert r.status_code == 201
        scan_id = r.json()["id"]

        upload = client.post(
            f"/api/scans/{scan_id}/image",
            files={"file": ("hy.png", _png_bytes(), "image/png")},
        )
        assert upload.status_code == 201
        body = upload.json()
        assert body["status"] == "completed"

        tool_runs = client.get(f"/api/scans/{scan_id}/tool-runs").json()
        tools = {t["tool"] for t in tool_runs["data"]}
        assert tools == {
            "photo-hash", "photo-phash", "photo-exif", "photo-qr",
            "photo-vision", "photo-nsfw", "photo-reverse-search",
        }
        vision = next(t for t in tool_runs["data"] if t["tool"] == "photo-vision")
        assert vision["status"] == "completed"

        findings = client.get(f"/api/scans/{scan_id}/findings").json()
        vision_findings = [f for f in findings["data"] if f["type"] == "image_vision"]
        assert len(vision_findings) == 1
        assert "green park" in vision_findings[0]["evidence"]

        assert worker_out.get("job_id"), "worker must pick up the vision job"
        assert worker_out.get("payload", {}).get("image_base64"), "image must travel to the worker"
        assert worker_out.get("post_status") == 200
        assert worker_out.get("processed") == 2, "vision + nsfw jobs both reach the worker"

        job = client.get(f"/api/jobs/{worker_out['internal_id']}").json()
        assert job["dataDeleted"] is True

        logs = client.get("/api/logs", params={"entityType": "job", "entityId": worker_out["internal_id"]}).json()
        details = {row["detail"] for row in logs["data"]}
        assert any("worker-pickup" in d for d in details)
        assert any("worker-result:completed" in d for d in details)
    finally:
        stop.set()
        thread.join(timeout=10)