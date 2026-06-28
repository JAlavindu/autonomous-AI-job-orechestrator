import pytest

from src.models.job import Job, JobStatus
from src.orchestrator.executors.base import ExecutionResult
import src.orchestrator.worker as worker


class FakeJobManager:
    """Records every status transition so we can assert on the sequence."""
    def __init__(self, job: Job):
        self._job = job
        self.status_calls: list = []

    def get_job(self, job_id: str):
        return self._job

    def update_job_status(self, job_id: str, status, worker_id=None):
        self.status_calls.append(status)
        self._job.status = status
        return self._job


def _pop_once_then_stop(job_id: str):
    """Yield one job id, then raise KeyboardInterrupt to exit the worker loop.

    KeyboardInterrupt is a BaseException, so the worker's `except Exception`
    does not catch it and the loop terminates cleanly for the test.
    """
    calls = {"n": 0}

    def _pop():
        if calls["n"] == 0:
            calls["n"] += 1
            return job_id
        raise KeyboardInterrupt

    return _pop


def test_failed_job_is_not_overwritten_as_completed(monkeypatch):
    job = Job(
        name="failing-job",
        estimated_duration=1,
        payload={"type": "shell", "command": "exit 1"},
    )
    fake_mgr = FakeJobManager(job)

    monkeypatch.setattr(worker, "job_manager", fake_mgr)
    monkeypatch.setattr(worker.redis_client, "pop_from_queue", _pop_once_then_stop(job.id))
    monkeypatch.setattr(
        worker, "execute_job",
        lambda j: ExecutionResult(success=False, exit_code=1, error_message="boom"),
    )

    with pytest.raises(KeyboardInterrupt):
        worker.run_worker("test-worker")

    # Final state is FAILED and COMPLETED was never recorded (the B2 regression).
    assert fake_mgr.status_calls[-1] == JobStatus.FAILED
    assert JobStatus.COMPLETED not in fake_mgr.status_calls


def test_worker_does_not_sleep_for_estimated_duration(monkeypatch):
    job = Job(
        name="sleepy-job",
        estimated_duration=999,  # would hang the test if the old redundant sleep returned
        payload={"type": "shell", "command": "echo hi"},
    )
    fake_mgr = FakeJobManager(job)
    sleep_calls: list = []

    monkeypatch.setattr(worker, "job_manager", fake_mgr)
    monkeypatch.setattr(worker.redis_client, "pop_from_queue", _pop_once_then_stop(job.id))
    monkeypatch.setattr(
        worker, "execute_job",
        lambda j: ExecutionResult(success=True, exit_code=0, stdout="hi"),
    )
    monkeypatch.setattr(worker.time, "sleep", lambda s: sleep_calls.append(s))

    with pytest.raises(KeyboardInterrupt):
        worker.run_worker("test-worker")

    assert fake_mgr.status_calls[-1] == JobStatus.COMPLETED
    # The redundant time.sleep(estimated_duration) must be gone.
    assert sleep_calls == []