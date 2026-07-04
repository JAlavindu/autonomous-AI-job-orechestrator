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


def test_list_jobs_paginated(api_client):
    api_client.post("/api/v1/jobs/", json={"name": "A", "estimated_duration": 1})
    api_client.post("/api/v1/jobs/", json={"name": "B", "estimated_duration": 1})

    response = api_client.get("/api/v1/jobs/?limit=1&offset=0")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 1
    assert body["limit"] == 1
    assert body["offset"] == 0


def test_idempotency_key(api_client):
    payload = {
        "name": "Idempotent Job",
        "estimated_duration": 1,
        "idempotency_key": "idem-123",
    }
    first = api_client.post("/api/v1/jobs/", json=payload)
    second = api_client.post("/api/v1/jobs/", json=payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


def test_submit_dag(api_client):
    payload = {
        "jobs": [
            {"key": "root", "name": "Root", "estimated_duration": 1, "depends_on": []},
            {"key": "child", "name": "Child", "estimated_duration": 1, "depends_on": ["root"]},
        ]
    }
    response = api_client.post("/api/v1/jobs/dag", json=payload)
    assert response.status_code == 201
    jobs = response.json()["jobs"]
    assert len(jobs) == 2
    child = next(j for j in jobs if j["name"] == "Child")
    root = next(j for j in jobs if j["name"] == "Root")
    assert root["id"] in child["dependencies"]


def test_cancel_job(api_client):
    create_res = api_client.post(
        "/api/v1/jobs/",
        json={"name": "Cancel Me", "estimated_duration": 1},
    )
    job_id = create_res.json()["id"]
    cancel_res = api_client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"