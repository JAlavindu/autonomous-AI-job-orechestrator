from fastapi.testclient import TestClient

from src.main import app


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ready_endpoint_reports_checks():
    client = TestClient(app)
    response = client.get("/ready")
    body = response.json()
    assert "checks" in body
    assert "postgres" in body["checks"]
    assert "redis" in body["checks"]