import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.api.admin_routes as admin_routes
import src.api.routes as routes
import src.auth.deps as auth_deps
import src.tenancy.rate_limit as rate_limit_mod
import src.db.models  # noqa: F401
import src.api.auth_routes as auth_routes
from src.auth.service_account_service import ServiceAccountService
from src.auth.service import ApiKeyService
from src.core import config
from src.db.base import Base
from src.main import app
from src.models.auth import Role
from src.orchestrator.job_manager import JobManager
from src.tenancy.policy import tenant_policy


@pytest.fixture
def api_client(monkeypatch):
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

    routes.job_manager = JobManager(session_factory=TestingSession)
    tenant_policy.session_factory = TestingSession

    key_service = ApiKeyService(session_factory=TestingSession)
    monkeypatch.setattr(auth_deps, "api_key_service", key_service)
    monkeypatch.setattr(admin_routes, "api_key_service", key_service)
    sa_service = ServiceAccountService(session_factory=TestingSession)
    monkeypatch.setattr(admin_routes, "service_account_service", sa_service)
    monkeypatch.setattr(auth_routes, "service_account_service", sa_service)
    _, operator_key = key_service.create_key("test-operator", Role.OPERATOR)
    _, viewer_key = key_service.create_key("test-viewer", Role.VIEWER)

    client = TestClient(app)
    client.operator_headers = {"X-API-Key": operator_key}
    client.session_factory = TestingSession
    client.viewer_headers = {"X-API-Key": viewer_key}

    try:
        yield client
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()