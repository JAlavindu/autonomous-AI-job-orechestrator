from fastapi.testclient import TestClient
from src.main import app
from src.db.redis_store import redis_client

client = TestClient(app)

def setup_module(module):
    """Run before tests: Clean DB"""
    redis_client.client.flushall()

def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Autonomous AI Job Orchestrator is running"}

def test_create_job():
    payload = {
        "name": "Unit Test Job",
        "priority": 5,
        "estimated_duration": 10
    }
    response = client.post("/api/v1/jobs/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Unit Test Job"
    assert "id" in data
    assert data["status"] == "PENDING"

def test_job_persistence():
    # Create a job
    payload = {"name": "Persistent Job", "priority": 10, "estimated_duration": 5}
    create_res = client.post("/api/v1/jobs/", json=payload)
    job_id = create_res.json()["id"]

    # Retrieve it
    get_res = client.get(f"/api/v1/jobs/{job_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == job_id
    assert get_res.json()["priority"] == 10

def test_get_nonexistent_job():
    response = client.get("/api/v1/jobs/non-existent-id")
    assert response.status_code == 404