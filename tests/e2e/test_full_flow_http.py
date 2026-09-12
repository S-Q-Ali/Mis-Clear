"""Phase 14 E2E: full investigation journey over real HTTP (uvicorn + httpx).

Adjusts a fresh scan end-to-end exactly as the SPA would: create, run, inspect
findings/tool-runs/graph/risk, run deletion research, approve an action, and
verify the audit log captured the whole chain.
"""

from __future__ import annotations


def test_full_investigation_flow_http(http):
    client, _ = http

    r = client.post("/api/scans", json={"targetType": "email", "targetValue": "alice@example.com"})
    assert r.status_code == 201
    scan_id = r.json()["id"]

    run = client.post(f"/api/scans/{scan_id}/run")
    assert run.status_code == 200
    body = run.json()
    assert body["status"] == "completed"
    assert body["coverage"]["tools_ran"] == 2
    assert body["coverage"]["findings"] == 1

    findings = client.get(f"/api/scans/{scan_id}/findings").json()
    assert findings["pagination"]["totalItems"] == 1
    assert findings["data"][0]["tool"] == "fakemail"

    tool_runs = client.get(f"/api/scans/{scan_id}/tool-runs").json()
    assert tool_runs["pagination"]["totalItems"] == 2

    graph = client.get(f"/api/scans/{scan_id}/graph").json()
    assert graph["nodes"] and graph["edges"]

    risk = client.get(f"/api/scans/{scan_id}/risk").json()
    assert isinstance(risk["riskScore"], int)
    assert risk["level"] in {"negligible", "low", "medium", "high", "critical"}

    research = client.post(f"/api/scans/{scan_id}/deletion-research").json()
    assert research["created"] >= 1
    assert research["researchable"] == 1

    actions = client.get("/api/actions").json()
    pending = [a for a in actions["data"] if a["findingId"] == findings["data"][0]["id"]]
    assert pending, "research must produce a pending action for the finding"
    action_id = pending[0]["id"]

    approved = client.post(f"/api/actions/{action_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    logs = client.get("/api/logs", params={"entityType": "scan", "entityId": scan_id}).json()
    details = {row["detail"] for row in logs["data"]}
    assert "email:alice@example.com" in details, "audit trail must capture creation"


def test_scan_list_supports_pagination_and_status_filter(http):
    client, _ = http
    for i in range(3):
        client.post("/api/scans", json={"targetType": "email", "targetValue": f"u{i}@example.com"})

    page = client.get("/api/scans", params={"page": 1, "pageSize": 2}).json()
    assert page["pagination"]["totalItems"] == 3
    assert len(page["data"]) == 2

    filtered = client.get("/api/scans", params={"status": "pending"}).json()
    assert filtered["pagination"]["totalItems"] == 3


def test_get_report_renders_after_run(http):
    client, _ = http
    r = client.post("/api/scans", json={"targetType": "email", "targetValue": "bob@example.com"})
    scan_id = r.json()["id"]
    client.post(f"/api/scans/{scan_id}/run")

    report = client.get(f"/api/reports/{scan_id}")
    assert report.status_code == 200
    body = report.json()
    assert body["scan"]["id"] == scan_id
    assert body["totalFindings"] == 1
    assert set(body["sourcesChecked"]) <= {"fakemail", "fakesearch"}
    assert body["aiAvailable"] is False