import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.api.admin_routes as admin_routes
import src.api.routes as routes
import src.auth.deps as auth_deps
import src.tenancy.policy as tenant_policy_mod
import src.tenancy.rate_limit as rate_limit_mod
import src.db.models  # noqa: F401
from src.auth.service import ApiKeyService
from src.core import config
from src.db.base import Base
from src.db.models import TenantRow
from src.main import app
from src.models.auth import Role
from src.models.job import JobCreate
from src.orchestrator.job_manager import JobManager
from src.tenancy.policy import tenant_policy
from fastapi.testclient import TestClient

TENANT_B = "00000000-0000-0000-0000-000000000002"


@pytest.fixture
def tenant_clients(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("API_KEY_PEPPER", "test-pepper")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    config.settings = config.Settings()
    monkeypatch.setattr(auth_deps, "settings", config.settings)
    monkeypatch.setattr(rate_limit_mod, "settings", config.settings)

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

    with TestingSession() as db:
        db.add(TenantRow(id=TENANT_B, name="tenant-b", max_jobs=100, rate_limit=1000, executor_allowlist="sleep"))
        db.commit()

    routes.job_manager = JobManager(session_factory=TestingSession)
    tenant_policy.session_factory = TestingSession
    key_service = ApiKeyService(session_factory=TestingSession)
    monkeypatch.setattr(auth_deps, "api_key_service", key_service)
    monkeypatch.setattr(admin_routes, "api_key_service", key_service)

    _, key_a = key_service.create_key("tenant-a-op", Role.OPERATOR)
    _, key_b = key_service.create_key("tenant-b-op", Role.OPERATOR, tenant_id=TENANT_B)

    client = TestClient(app)
    client.headers_a = {"X-API-Key": key_a}
    client.headers_b = {"X-API-Key": key_b}

    yield client

    Base.metadata.drop_all(engine)
    engine.dispose()


def test_tenant_b_cannot_read_tenant_a_job(tenant_clients):
    create = tenant_clients.post(
        "/api/v1/jobs/",
        json={"name": "secret", "estimated_duration": 1},
        headers=tenant_clients.headers_a,
    )
    assert create.status_code == 201
    job_id = create.json()["id"]

    get_b = tenant_clients.get(f"/api/v1/jobs/{job_id}", headers=tenant_clients.headers_b)
    assert get_b.status_code == 404


def test_tenant_jobs_are_list_isolated(tenant_clients):
    tenant_clients.post(
        "/api/v1/jobs/",
        json={"name": "A-job", "estimated_duration": 1},
        headers=tenant_clients.headers_a,
    )
    tenant_clients.post(
        "/api/v1/jobs/",
        json={"name": "B-job", "estimated_duration": 1},
        headers=tenant_clients.headers_b,
    )

    list_a = tenant_clients.get("/api/v1/jobs/", headers=tenant_clients.headers_a).json()
    list_b = tenant_clients.get("/api/v1/jobs/", headers=tenant_clients.headers_b).json()

    assert list_a["total"] == 1
    assert list_b["total"] == 1
    assert list_a["items"][0]["name"] == "A-job"
    assert list_b["items"][0]["name"] == "B-job"


def test_job_quota_enforced(tenant_clients, monkeypatch):
    monkeypatch.setenv("DEFAULT_TENANT_MAX_JOBS", "1")
    config.settings = config.Settings()
    monkeypatch.setattr(auth_deps, "settings", config.settings)
    monkeypatch.setattr(rate_limit_mod, "settings", config.settings)
    monkeypatch.setattr(tenant_policy_mod, "settings", config.settings)

    first = tenant_clients.post(
        "/api/v1/jobs/",
        json={"name": "one", "estimated_duration": 1},
        headers=tenant_clients.headers_a,
    )
    assert first.status_code == 201

    second = tenant_clients.post(
        "/api/v1/jobs/",
        json={"name": "two", "estimated_duration": 1},
        headers=tenant_clients.headers_a,
    )
    assert second.status_code == 429