"""Phase 14 E2E: Colab worker protocol flow over real HTTP.

Simulates the Colab worker lifecycle against the real laptop control plane:
    laptop:  POST /api/jobs          (user creates a job)
    colab:   GET  /api/jobs/next     (worker picks up the oldest queued job)
    colab:   POST /api/jobs/{id}/result  (worker returns JobResult)
    laptop:  GET  /api/jobs/{id}     (verify persisted status=completed + data_deleted)
    laptop:  GET  /api/logs          (audit trail captured both transitions)

No real Colab is needed: httpx is the transport, exactly as colab/dispatch.py uses.
"""

from __future__ import annotations


def test_colab_worker_pickup_and_result(http):
    client, _ = http

    # --- 1. User creates a job on the laptop ---
    create = client.post("/api/jobs", json={
        "jobId": "colab-e2e-1",
        "jobType": "reasoning",
        "privacyMode": "hybrid_approved",
        "payload": {"prompt": "What is 2+2?", "model": "qwen3:8b"},
        "requestedCapabilities": ["reasoning"],
    })
    assert create.status_code == 201
    assert create.json()["status"] == "queued"

    # --- 2. Colab worker polls GET /next → picks up the job ---
    nxt = client.get("/api/jobs/next")
    assert nxt.status_code == 200
    body = nxt.json()
    assert body["job_id"] == "colab-e2e-1"
    assert body["job_type"] == "reasoning"
    assert body["protocol_version"] == "1"
    assert body["privacy_mode"] == "hybrid_approved"
    internal_id = body["_internal_id"]

    # Job is now "running" on the laptop side.
    job = client.get(f"/api/jobs/{internal_id}").json()
    assert job["status"] == "running"

    # --- 3. A second GET /next returns 204 (no more queued jobs) ---
    empty = client.get("/api/jobs/next")
    assert empty.status_code == 204

    # --- 4. Colab worker POSTs the JobResult ---
    result = client.post(f"/api/jobs/colab-e2e-1/result", json={
        "protocol_version": "1",
        "job_id": "colab-e2e-1",
        "status": "completed",
        "started_at": "2026-01-01T00:00:00+00:00",
        "completed_at": "2026-01-01T00:00:05+00:00",
        "result": {"ok": True, "text": "2+2=4", "model": "qwen3:8b"},
        "errors": [],
        "data_deleted": True,
    })
    assert result.status_code == 200
    assert result.json() == {"ok": True, "job_id": "colab-e2e-1", "status": "completed"}

    # --- 5. Laptop reflects the persisted result ---
    job = client.get(f"/api/jobs/{internal_id}").json()
    assert job["status"] == "completed"
    assert job["dataDeleted"] is True
    assert job["result"]["text"] == "2+2=4"

    # --- 6. Audit trail captured both transitions ---
    logs = client.get("/api/logs", params={"entityType": "job", "entityId": internal_id}).json()
    details = {row["detail"] for row in logs["data"]}
    assert any("worker-pickup" in d for d in details)
    assert any("worker-result:completed" in d for d in details)


def test_colab_worker_reports_failure(http):
    client, _ = http

    client.post("/api/jobs", json={
        "jobId": "colab-e2e-fail",
        "jobType": "ocr",
        "privacyMode": "hybrid_approved",
        "payload": {"imageRef": "img-1"},
    })

    nxt = client.get("/api/jobs/next")
    assert nxt.status_code == 200
    body = nxt.json()
    internal_id = body["_internal_id"]

    result = client.post(f"/api/jobs/colab-e2e-fail/result", json={
        "job_id": "colab-e2e-fail",
        "status": "failed",
        "errors": ["GPU OOM: image too large"],
        "data_deleted": True,
    })
    assert result.status_code == 200

    job = client.get(f"/api/jobs/{internal_id}").json()
    assert job["status"] == "failed"
    assert job["errors"] == ["GPU OOM: image too large"]


def test_get_next_returns_204_when_no_queued_jobs(http):
    client, _ = http
    resp = client.get("/api/jobs/next")
    assert resp.status_code == 204


def test_result_rejects_invalid_status(http):
    client, _ = http

    client.post("/api/jobs", json={
        "jobId": "colab-e2e-badstatus",
        "jobType": "reasoning",
        "payload": {},
    })
    nxt = client.get("/api/jobs/next")
    assert nxt.status_code == 200

    resp = client.post(f"/api/jobs/colab-e2e-badstatus/result", json={
        "job_id": "colab-e2e-badstatus",
        "status": "fake_status",
    })
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_STATUS"