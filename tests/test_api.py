from src.models.job import JobStatus
from src.orchestrator.executors.base import ExecutionResult


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
    response = api_client.post(
        "/api/v1/jobs/", json=payload, headers=api_client.operator_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Unit Test Job"
    assert "id" in data
    assert data["status"] == "PENDING"


def test_job_persistence(api_client):
    payload = {"name": "Persistent Job", "priority": 10, "estimated_duration": 5}
    create_res = api_client.post(
        "/api/v1/jobs/", json=payload, headers=api_client.operator_headers
    )
    job_id = create_res.json()["id"]

    get_res = api_client.get(
        f"/api/v1/jobs/{job_id}", headers=api_client.operator_headers
    )
    assert get_res.status_code == 200
    assert get_res.json()["id"] == job_id
    assert get_res.json()["priority"] == 10


def test_get_nonexistent_job(api_client):
    response = api_client.get(
        "/api/v1/jobs/non-existent-id", headers=api_client.operator_headers
    )
    assert response.status_code == 404


def test_list_jobs_paginated(api_client):
    api_client.post(
        "/api/v1/jobs/",
        json={"name": "A", "estimated_duration": 1},
        headers=api_client.operator_headers,
    )
    api_client.post(
        "/api/v1/jobs/",
        json={"name": "B", "estimated_duration": 1},
        headers=api_client.operator_headers,
    )

    response = api_client.get(
        "/api/v1/jobs/?limit=1&offset=0", headers=api_client.operator_headers
    )
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
    first = api_client.post(
        "/api/v1/jobs/", json=payload, headers=api_client.operator_headers
    )
    second = api_client.post(
        "/api/v1/jobs/", json=payload, headers=api_client.operator_headers
    )
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
    response = api_client.post(
        "/api/v1/jobs/dag", json=payload, headers=api_client.operator_headers
    )
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
        headers=api_client.operator_headers,
    )
    job_id = create_res.json()["id"]
    cancel_res = api_client.post(
        f"/api/v1/jobs/{job_id}/cancel", headers=api_client.operator_headers
    )
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"


def test_get_run_logs_preview(api_client):
    create_res = api_client.post(
        "/api/v1/jobs/",
        json={"name": "Log Job", "estimated_duration": 1},
        headers=api_client.operator_headers,
    )
    job_id = create_res.json()["id"]

    from src.api import routes

    manager = routes.job_manager
    run = manager.start_run(job_id, "worker-a")
    manager.finish_run(
        run.id,
        JobStatus.COMPLETED,
        ExecutionResult(success=True, exit_code=0, stdout="hello"),
    )

    response = api_client.get(
        f"/api/v1/jobs/{job_id}/runs/{run.id}/logs",
        headers=api_client.operator_headers,
    )
    assert response.status_code == 200
    assert response.json()["stdout"] == "hello"


def test_list_dlq(api_client, monkeypatch):
    monkeypatch.setattr(
        "src.orchestrator.job_manager.job_stream.list_dlq",
        lambda count=100: [{"message_id": "1-0", "job_id": "abc", "reason": "boom"}],
    )
    response = api_client.get("/api/v1/dlq", headers=api_client.operator_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_unauthenticated_request_rejected(api_client, monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    from src.core import config

    config.settings = config.Settings()

    response = api_client.get("/api/v1/jobs/")
    assert response.status_code == 401


def test_viewer_cannot_create_job(api_client):
    response = api_client.post(
        "/api/v1/jobs/",
        json={"name": "Nope", "estimated_duration": 1},
        headers=api_client.viewer_headers,
    )
    assert response.status_code == 403


def test_viewer_can_list_jobs(api_client):
    api_client.post(
        "/api/v1/jobs/",
        json={"name": "Visible", "estimated_duration": 1},
        headers=api_client.operator_headers,
    )
    response = api_client.get("/api/v1/jobs/", headers=api_client.viewer_headers)
    assert response.status_code == 200


def test_viewer_cannot_list_dlq(api_client):
    response = api_client.get("/api/v1/dlq", headers=api_client.viewer_headers)
    assert response.status_code == 403


def test_operator_can_create_api_key(api_client):
    response = api_client.post(
        "/api/v1/admin/api-keys",
        json={"name": "ci-key", "role": "producer"},
        headers=api_client.operator_headers,
    )
    assert response.status_code == 201
    assert response.json()["api_key"].startswith("ork_")
