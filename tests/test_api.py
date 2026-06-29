import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.api.routes as routes
import src.db.models  # noqa: F401
from src.db.base import Base
from src.main import app
from src.orchestrator.job_manager import JobManager


@pytest.fixture
def api_client(monkeypatch):
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
    manager = JobManager(session_factory=TestingSession)
    monkeypatch.setattr(routes, "job_manager", manager)

    try:
        yield TestClient(app)
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_root(api_client):
    response = api_client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Autonomous AI Job Orchestrator is running"}


def test_create_job(api_client):
    payload = {
        "name": "Unit Test Job",
        "priority": 5,
        "estimated_duration": 10,
    }
    response = api_client.post("/api/v1/jobs/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Unit Test Job"
    assert "id" in data
    assert data["status"] == "PENDING"


def test_job_persistence(api_client):
    payload = {"name": "Persistent Job", "priority": 10, "estimated_duration": 5}
    create_res = api_client.post("/api/v1/jobs/", json=payload)
    job_id = create_res.json()["id"]

    get_res = api_client.get(f"/api/v1/jobs/{job_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == job_id
    assert get_res.json()["priority"] == 10


def test_get_nonexistent_job(api_client):
    response = api_client.get("/api/v1/jobs/non-existent-id")
    assert response.status_code == 404
