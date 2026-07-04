import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.api.routes as routes
import src.db.models  # noqa: F401
from src.auth.service import ApiKeyService
from src.core import config
from src.db.base import Base
from src.main import app
from src.models.auth import Role
from src.orchestrator.job_manager import JobManager


@pytest.fixture
def api_client(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("API_KEY_PEPPER", "test-pepper")
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

    routes.job_manager = JobManager(session_factory=TestingSession)

    key_service = ApiKeyService(session_factory=TestingSession)
    _, operator_key = key_service.create_key("test-operator", Role.OPERATOR)
    _, viewer_key = key_service.create_key("test-viewer", Role.VIEWER)

    client = TestClient(app)
    client.operator_headers = {"X-API-Key": operator_key}
    client.viewer_headers = {"X-API-Key": viewer_key}

    try:
        yield client
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()