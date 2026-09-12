"""Phase 8: worker lifecycle tests (protocol compliance, temp hygiene, none network)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from colab import worker
from colab.capabilities import CapabilityReport
from colab.protocol import JobRequest


def _caps():
    return CapabilityReport(gpu=False, models=[])


def _job(job_id="job-1", job_type="tests_echo", expires_at="") -> JobRequest:
    return JobRequest(job_id=job_id, job_type=job_type, payload={"value": 1}, expires_at=expires_at)


def test_execute_job_completed_and_temp_cleaned(tmp_path):
    from pathlib import Path as _Path

    def handler(payload, caps):
        tmp = _Path(payload["tmp_dir"])
        (tmp / "secret.txt").write_text("x")
        return {"ok": True, "echo": payload["value"]}

    worker.register_worker_handler("tests_echo", handler)
    job = _job()
    result, detail = worker.execute_job(job, caps=_caps(), tmp_root=tmp_path)
    assert result.status == "completed", f"status={result.status} errors={result.errors}"
    assert result.data_deleted is True
    assert result.result == {"ok": True, "echo": 1}
    assert not (tmp_path / "job-1").exists()
    assert not (tmp_path / "job-1" / "secret.txt").exists()
    assert detail["echo"] == 1


def test_execute_job_unsupported_protocol(tmp_path):
    result, _ = worker.execute_job(
        JobRequest(job_id="x", job_type="tests_echo", protocol_version="2"),
        caps=_caps(),
        tmp_root=tmp_path,
    )
    assert result.status == "failed"
    assert result.errors and "protocol_version" in result.errors[0]
    assert result.data_deleted is False


def test_execute_job_expires_before_processing(tmp_path):
    past = (datetime.now(UTC) - timedelta(seconds=30)).isoformat()
    result, _ = worker.execute_job(_job(expires_at=past), caps=_caps(), tmp_root=tmp_path)
    assert result.status == "interrupted"
    assert "expired" in result.errors[0]
    assert result.data_deleted is False


def test_execute_job_unknown_type(tmp_path):
    result, _ = worker.execute_job(_job(job_type="nope_nope"), caps=_caps(), tmp_root=tmp_path)
    assert result.status == "failed"
    assert "no handler" in result.errors[0]


def test_execute_job_handler_crash_isolated_and_cleanup(tmp_path):
    def bad(payload, caps):
        raise RuntimeError("kaboom")

    worker.register_worker_handler("tests_crash", bad)
    result, _ = worker.execute_job(_job(job_type="tests_crash"), caps=_caps(), tmp_root=tmp_path)
    assert result.status == "failed"
    assert result.errors[0].startswith("RuntimeError")
    assert result.data_deleted is True


def test_execute_job_future_expiry_processes(tmp_path):
    future = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
    result, _ = worker.execute_job(_job(expires_at=future), caps=_caps(), tmp_root=tmp_path)
    assert result.status == "completed"


def test_fetch_next_job_parses_request():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_job(job_id="remote-1", job_type="tests_echo").to_dict())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    job = worker.fetch_next_job("https://dispatcher.test", caps=_caps(), client=client)
    assert job is not None
    assert job.job_id == "remote-1"
    assert job.job_type == "tests_echo"


def test_fetch_next_job_empty_returns_none():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(204)))
    job = worker.fetch_next_job("https://dispatcher.test", caps=_caps(), client=client)
    assert job is None


def test_submit_result_ack(tmp_path):
    import json as _json

    def handler(request: httpx.Request) -> httpx.Response:
        assert "/jobs/job-ack/result" in request.url.path
        body = _json.loads(request.content)
        assert body["status"] == "completed"
        assert body["data_deleted"] is True
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result, _ = worker.execute_job(_job(job_id="job-ack"), caps=_caps(), tmp_root=tmp_path)
    result.status = "completed"
    result.data_deleted = True
    assert worker.submit_result("https://dispatcher.test", result, client=client) is True


def test_run_worker_main_processes_one_job(tmp_path, monkeypatch):
    calls = {"n": 0}

    def fake_fetch(url, caps=None, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return _job(job_id="main-1", job_type="tests_echo")
        return None

    monkeypatch.setattr(worker, "fetch_next_job", fake_fetch)
    monkeypatch.setattr(worker, "execute_job", lambda job, **kw: (worker.JobResult(job_id=job.job_id, status="completed", data_deleted=True), {"ok": True}))
    submitted = []
    monkeypatch.setattr(worker, "submit_result", lambda url, result, **kw: submitted.append(result.job_id) or True)

    summary = worker.run_worker_main("https://dispatcher.test", caps=_caps(), tmp_root=tmp_path, max_iterations=3)
    assert summary["jobs_processed"] == 1
    assert submitted == ["main-1"]


def test_run_worker_main_reconnects_then_gives_up(tmp_path, monkeypatch):
    calls = {"n": 0}

    def broken_fetch(url, caps=None, **k):
        calls["n"] += 1
        raise httpx.ConnectError("down")

    monkeypatch.setattr(worker, "fetch_next_job", broken_fetch)
    monkeypatch.setattr(worker, "submit_result", lambda *a, **k: True)

    summary = worker.run_worker_main(
        "https://dispatcher.test", caps=_caps(), tmp_root=tmp_path,
        max_iterations=10, max_failures=3,
    )
    assert summary["jobs_processed"] == 0
    assert summary["reconnects"] >= 3
    assert "unreachable" in summary.get("note", "")