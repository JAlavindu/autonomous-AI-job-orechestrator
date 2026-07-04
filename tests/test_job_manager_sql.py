import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.db.models  # noqa: F401
from src.core.config import settings
from src.db.base import Base
from src.db.models import AuditLogRow, DependencyRow, RunRow
from src.models.job import JobCreate, JobStatus
from src.tenancy.policy import tenant_policy
from src.orchestrator.executors.base import ExecutionResult
from src.orchestrator.job_manager import JobManager


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


def test_create_get_and_list_jobs_persist_in_sql(manager):
    created = manager.create_job(
        JobCreate(name="sql-job", priority=7, estimated_duration=3, payload={"type": "sleep"})
    , tenant_id=settings.DEFAULT_TENANT_ID)

    fetched = manager.get_job(created.id)
    listed, total = manager.list_jobs()
    assert total == 1
    assert [job.id for job in listed] == [created.id]

    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.name == "sql-job"
    assert fetched.priority == 7
    assert fetched.payload == {"type": "sleep"}
    assert [job.id for job in listed] == [created.id]


def test_dependencies_are_stored_and_gated(manager, session_factory):
    parent = manager.create_job(JobCreate(name="parent", estimated_duration=1), tenant_id=settings.DEFAULT_TENANT_ID)
    child = manager.create_job(
        JobCreate(name="child", estimated_duration=1, dependencies=[parent.id])
    , tenant_id=settings.DEFAULT_TENANT_ID)

    with session_factory() as db:
        edges = db.scalars(select(DependencyRow).where(DependencyRow.job_id == child.id)).all()
        assert len(edges) == 1
        assert edges[0].depends_on_job_id == parent.id

    assert manager.are_dependencies_met(child) is False
    manager.update_job_status(parent.id, JobStatus.COMPLETED)
    assert manager.are_dependencies_met(manager.get_job(child.id)) is True


def test_status_transitions_update_timestamps_and_audit(manager, session_factory):
    job = manager.create_job(JobCreate(name="transition", estimated_duration=1), tenant_id=settings.DEFAULT_TENANT_ID)

    running = manager.update_job_status(job.id, JobStatus.RUNNING, worker_id="worker-a")
    completed = manager.update_job_status(job.id, JobStatus.COMPLETED)

    assert running.started_at is not None
    assert running.worker_id == "worker-a"
    assert completed.completed_at is not None

    with session_factory() as db:
        actions = [row.action for row in db.scalars(select(AuditLogRow)).all()]
        assert "job.created" in actions
        assert actions.count("job.status_changed") == 2


def test_run_attempts_are_persisted(manager, session_factory):
    job = manager.create_job(JobCreate(name="run-me", estimated_duration=1), tenant_id=settings.DEFAULT_TENANT_ID)

    run = manager.start_run(job.id, "worker-a")
    result = ExecutionResult(
        success=False,
        exit_code=2,
        stdout="out",
        stderr="err",
        duration_seconds=0.5,
        error_message="boom",
    )
    manager.finish_run(run.id, JobStatus.FAILED, result)

    with session_factory() as db:
        rows = db.scalars(select(RunRow).where(RunRow.job_id == job.id)).all()
        assert len(rows) == 1
        assert rows[0].attempt == 1
        assert rows[0].status == "FAILED"
        assert rows[0].exit_code == 2
        assert rows[0].stdout == "out"
        assert rows[0].stderr == "err"
        assert rows[0].metrics == {"duration_seconds": 0.5}
