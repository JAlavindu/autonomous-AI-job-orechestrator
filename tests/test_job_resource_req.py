import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.db.models  # noqa: F401
from src.core.config import settings
from src.db.base import Base
from src.models.job import JobCreate, ResourceReq
from src.orchestrator.job_manager import JobManager
from src.tenancy.policy import tenant_policy


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
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True
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


def test_resource_req_round_trips(manager):
    created = manager.create_job(
        JobCreate(
            name="limited",
            estimated_duration=1,
            payload={"type": "sleep"},
            resource_req=ResourceReq(timeout_seconds=30, memory_mb=128),
        ),
        tenant_id=settings.DEFAULT_TENANT_ID,
    )
    fetched = manager.get_job(created.id)
    assert fetched.resource_req is not None
    assert fetched.resource_req.timeout_seconds == 30
    assert fetched.resource_req.memory_mb == 128
    assert fetched.resource_req.cpu_seconds is None  # unset, excluded on write


def test_resource_req_defaults_to_none(manager):
    created = manager.create_job(
        JobCreate(name="plain", estimated_duration=1, payload={"type": "sleep"}),
        tenant_id=settings.DEFAULT_TENANT_ID,
    )
    assert manager.get_job(created.id).resource_req is None
