import threading

import pytest
from dataclasses import dataclass

from src.models.job import Job, JobStatus
from src.orchestrator.executors.base import ExecutionResult
import src.orchestrator.worker as worker


@dataclass(frozen=True)
class FakeMessage:
    message_id: str
    job_id: str


class FakeJobManager:
    def __init__(self, job: Job):
        self._job = job
        self.status_calls: list = []
        self.acked: list[str] = []

    def get_job(self, job_id: str):
        return self._job

    def update_job_status(self, job_id: str, status, worker_id=None):
        self.status_calls.append(status)
        self._job.status = status
        return self._job

    def start_run(self, job_id: str, worker_id: str):
        return type("Run", (), {"id": "run-1"})()

    def finish_run(self, run_id: str, status, result):
        return None

    def handle_execution_failure(self, job_id, run_id, result, source_message_id=None):
        self.finish_run(run_id, JobStatus.FAILED, result)
        self.update_job_status(job_id, JobStatus.FAILED)
        return "failed", 0.0

    def get_executor_allowlist_for_job(self, job_id: str):
        return {"shell", "sleep"}


def _read_once_then_stop(job_id: str):
    calls = {"n": 0}

    def _read(consumer_name: str):
        if calls["n"] == 0:
            calls["n"] += 1
            return FakeMessage(message_id="1-0", job_id=job_id)
        raise KeyboardInterrupt

    return _read


def _patch_lease(monkeypatch):
    monkeypatch.setattr(worker.lease_store, "acquire", lambda job_id, worker_id, ttl_seconds=None: True)
    monkeypatch.setattr(worker.lease_store, "renew", lambda job_id, worker_id, ttl_seconds=None: True)
    monkeypatch.setattr(worker.lease_store, "release", lambda job_id, worker_id: None)
    monkeypatch.setattr(worker.lease_store, "get_holder", lambda job_id: None)


def _patch_stream(monkeypatch, job_id: str, fake_mgr: FakeJobManager):
    monkeypatch.setattr(worker.job_stream, "ensure_group", lambda: None)
    monkeypatch.setattr(worker.job_stream, "read", _read_once_then_stop(job_id))
    monkeypatch.setattr(worker.job_stream, "claim_stale_messages", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        worker.job_stream,
        "ack",
        lambda message_id: fake_mgr.acked.append(message_id) or 1,
    )
    monkeypatch.setattr(worker, "job_manager", fake_mgr)
    _patch_lease(monkeypatch)

    def _immediate_stop(job_id: str, worker_id: str) -> threading.Event:
        stop = threading.Event()
        stop.set()
        return stop

    monkeypatch.setattr(worker, "_start_heartbeat", _immediate_stop)


def test_failed_job_is_not_overwritten_as_completed(monkeypatch):
    job = Job(
        name="failing-job",
        estimated_duration=1,
        payload={"type": "shell", "command": "exit 1"},
    )
    fake_mgr = FakeJobManager(job)
    _patch_stream(monkeypatch, job.id, fake_mgr)
    monkeypatch.setattr(
        worker.runner,
        "run",
        lambda j, executor_allowlist=None: ExecutionResult(
            success=False, exit_code=1, error_message="boom"
        ),
    )

    with pytest.raises(KeyboardInterrupt):
        worker.run_worker("test-worker")

    assert fake_mgr.status_calls[-1] == JobStatus.FAILED
    assert JobStatus.COMPLETED not in fake_mgr.status_calls
    assert fake_mgr.acked == ["1-0"]


def test_worker_does_not_sleep_for_estimated_duration(monkeypatch):
    job = Job(
        name="sleepy-job",
        estimated_duration=999,
        payload={"type": "shell", "command": "echo hi"},
    )
    fake_mgr = FakeJobManager(job)
    sleep_calls: list = []

    _patch_stream(monkeypatch, job.id, fake_mgr)
    monkeypatch.setattr(
        worker.runner,
        "run",
        lambda j, executor_allowlist=None: ExecutionResult(success=True, exit_code=0, stdout="hi"),
    )
    monkeypatch.setattr(worker.time, "sleep", lambda s: sleep_calls.append(s))

    with pytest.raises(KeyboardInterrupt):
        worker.run_worker("test-worker")

    assert fake_mgr.status_calls[-1] == JobStatus.COMPLETED
    assert sleep_calls == []
    assert fake_mgr.acked == ["1-0"]
