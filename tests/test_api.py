import pytest
import redis as redis_lib

from src.core.config import settings


def _redis_available() -> bool:
    try:
        client = redis_lib.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        client.ping()
        return True
    except (redis_lib.RedisError, OSError):
        return False


_REDIS_UP = _redis_available()
pytestmark = pytest.mark.skipif(
    not _REDIS_UP,
    reason="Redis not available (start with: docker compose up redis -d)",
)

if _REDIS_UP:
    from fastapi.testclient import TestClient

    from src.db.redis_store import redis_client
    from src.main import app

    client = TestClient(app)


def setup_module(module):
    if _REDIS_UP:
        redis_client.client.flushall()


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Autonomous AI Job Orchestrator is running"}


def test_create_job():
    payload = {
        "name": "Unit Test Job",
        "priority": 5,
        "estimated_duration": 10,
    }
    response = client.post("/api/v1/jobs/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Unit Test Job"
    assert "id" in data
    assert data["status"] == "PENDING"


def test_job_persistence():
    payload = {"name": "Persistent Job", "priority": 10, "estimated_duration": 5}
    create_res = client.post("/api/v1/jobs/", json=payload)
    job_id = create_res.json()["id"]

    get_res = client.get(f"/api/v1/jobs/{job_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == job_id
    assert get_res.json()["priority"] == 10


def test_get_nonexistent_job():
    response = client.get("/api/v1/jobs/non-existent-id")
    assert response.status_code == 404
