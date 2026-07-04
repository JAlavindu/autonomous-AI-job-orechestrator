import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.db.models  # noqa: F401
from src.core.config import settings
from src.db.base import Base
from src.db.models import RunRow
from src.models.job import JobCreate, JobStatus
from src.orchestrator.executors.base import ExecutionResult
from src.orchestrator.job_manager import JobManager
from src.storage.run_logs import load_full_run_logs, persist_run_output
from src.tenancy.policy import tenant_policy

TENANT = settings.DEFAULT_TENANT_ID


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_STORAGE_ROOT", str(tmp_path / "logs"))
    from src.core import config

    config.settings = config.Settings()

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
    tenant_policy.session_factory = TestingSession
    return JobManager(session_factory=TestingSession)


def test_persist_run_output_spills_large_stdout(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_STORAGE_ROOT", str(tmp_path / "logs"))
    from src.core import config

    config.settings = config.Settings()

    huge = "x" * 10000
    persisted = persist_run_output("run-1", huge, "", "")
    assert persisted.log_ref is not None
    assert "truncated" in (persisted.stdout or "")

    full = load_full_run_logs(persisted.log_ref, persisted.stdout, persisted.stderr, persisted.error)
    assert full["spilled"] is True
    assert full["stdout"] == huge


def test_finish_run_sets_log_ref(manager):
    job = manager.create_job(JobCreate(name="log-job", estimated_duration=1), tenant_id=TENANT)
    run = manager.start_run(job.id, "worker-a")
    huge = "y" * 10000
    manager.finish_run(
        run.id,
        JobStatus.COMPLETED,
        ExecutionResult(success=True, exit_code=0, stdout=huge),
    )

    with manager.session_factory() as db:
        row = db.scalar(select(RunRow).where(RunRow.id == run.id))
        assert row.log_ref is not None
        assert "truncated" in (row.stdout or "")

    logs = manager.get_run_logs(job.id, run.id, tenant_id=TENANT, full=True)
    assert logs["stdout"] == huge
