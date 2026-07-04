import pytest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.db.models  # noqa: F401
from src.db.base import Base
from src.db.models import JobRow
from src.core.config import settings
from src.models.job import DagJobCreate, JobCreate, JobStatus
from src.orchestrator.executors.base import ExecutionResult
from src.orchestrator.job_manager import JobManager
from src.tenancy.policy import tenant_policy

TENANT = settings.DEFAULT_TENANT_ID


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )
    try:
        yield TestingSession
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def manager(session_factory):
    tenant_policy.session_factory = session_factory
    return JobManager(session_factory=session_factory)


def test_idempotency_returns_existing_job(manager):
    payload = JobCreate(name="once", estimated_duration=1, idempotency_key="abc")
    first = manager.create_job(payload, tenant_id=TENANT)
    second = manager.create_job(payload, tenant_id=TENANT)
    assert first.id == second.id


def test_cancel_job(manager):
    job = manager.create_job(JobCreate(name="cancel-me", estimated_duration=1), tenant_id=TENANT)
    cancelled = manager.cancel_job(job.id, tenant_id=TENANT)
    assert cancelled.status == JobStatus.CANCELLED


def test_retry_job_from_failed(manager, monkeypatch):
    job = manager.create_job(JobCreate(name="retry-me", estimated_duration=1), tenant_id=TENANT)
    manager.update_job_status(job.id, JobStatus.FAILED)

    enqueued = []
    monkeypatch.setattr(manager, "enqueue_job", lambda job_id: enqueued.append(job_id) or "1-0")

    retried = manager.retry_job(job.id, tenant_id=TENANT)
    assert retried.status == JobStatus.PENDING
    assert enqueued == [job.id]


def test_handle_execution_failure_retries_then_dlq(manager, monkeypatch):
    job = manager.create_job(JobCreate(name="flaky", estimated_duration=1), tenant_id=TENANT)
    run = manager.start_run(job.id, "worker-a")
    result = ExecutionResult(success=False, exit_code=1, error_message="boom")

    dlq_calls = []
    monkeypatch.setattr(
        "src.orchestrator.job_manager.job_stream.send_to_dlq",
        lambda job_id, reason, source_message_id=None: dlq_calls.append((job_id, reason)) or "dlq-1",
    )

    with patch("src.orchestrator.job_manager.settings.MAX_JOB_RETRIES", 1):
        action, delay = manager.handle_execution_failure(job.id, run.id, result)
        assert action == "retry"
        assert delay >= 0

        job_after_retry = manager.get_job(job.id)
        assert job_after_retry.status == JobStatus.RETRYING
        assert job_after_retry.retry_count == 1

        run2 = manager.start_run(job.id, "worker-a")
        action2, _ = manager.handle_execution_failure(job.id, run2.id, result)
        assert action2 == "dlq"
        assert manager.get_job(job.id).status == JobStatus.FAILED
        assert len(dlq_calls) == 1


def test_create_dag(manager):
    jobs = manager.create_dag(
        [
            DagJobCreate(key="a", name="A", estimated_duration=1),
            DagJobCreate(key="b", name="B", estimated_duration=1, depends_on=["a"]),
        ],
        tenant_id=TENANT,
    )
    assert len(jobs) == 2
    child = next(j for j in jobs if j.name == "B")
    parent = next(j for j in jobs if j.name == "A")
    assert parent.id in child.dependencies


def test_finish_run_truncates_or_spills_output(manager):
    job = manager.create_job(JobCreate(name="big-output", estimated_duration=1), tenant_id=TENANT)
    run = manager.start_run(job.id, "worker-a")
    huge = "x" * 100_000
    manager.finish_run(
        run.id,
        JobStatus.COMPLETED,
        ExecutionResult(success=True, exit_code=0, stdout=huge),
    )
    runs, _ = manager.get_runs(job.id, tenant_id=TENANT)
    assert runs[0].log_ref is not None
    assert "truncated" in (runs[0].stdout or "")


def test_list_jobs_filter_and_count(manager):
    manager.create_job(JobCreate(name="p1", estimated_duration=1), tenant_id=TENANT)
    j2 = manager.create_job(JobCreate(name="p2", estimated_duration=1), tenant_id=TENANT)
    manager.update_job_status(j2.id, JobStatus.COMPLETED)

    pending, pending_total = manager.list_jobs(status=JobStatus.PENDING)
    completed, completed_total = manager.list_jobs(status=JobStatus.COMPLETED)

    assert pending_total == 1
    assert completed_total == 1
    assert pending[0].name == "p1"
    assert completed[0].name == "p2"