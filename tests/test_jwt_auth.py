def _create_service_account(api_client, name="ci-bot", role="producer"):
    resp = api_client.post(
        "/api/v1/admin/service-accounts",
        json={"name": name, "role": role},
        headers=api_client.operator_headers,
    )
    assert resp.status_code == 201
    return resp.json()


def _get_token(api_client, client_id, client_secret):
    return api_client.post(
        "/api/v1/auth/token",
        json={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )


def test_client_credentials_flow_end_to_end(api_client):
    sa = _create_service_account(api_client)

    token_resp = _get_token(api_client, sa["client_id"], sa["client_secret"])
    assert token_resp.status_code == 200
    body = token_resp.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0

    # The JWT works as a Bearer credential on a protected, role-gated endpoint.
    job_resp = api_client.post(
        "/api/v1/jobs/",
        json={"name": "jwt-job", "estimated_duration": 1, "payload": {"type": "sleep"}},
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert job_resp.status_code == 201


def test_bad_client_secret_rejected(api_client):
    sa = _create_service_account(api_client)
    resp = _get_token(api_client, sa["client_id"], "ssec_wrong")
    assert resp.status_code == 401


def test_revoked_service_account_cannot_get_token(api_client):
    sa = _create_service_account(api_client)
    del_resp = api_client.delete(
        f"/api/v1/admin/service-accounts/{sa['id']}",
        headers=api_client.operator_headers,
    )
    assert del_resp.status_code == 204
    resp = _get_token(api_client, sa["client_id"], sa["client_secret"])
    assert resp.status_code == 401


def test_viewer_cannot_create_service_account(api_client):
    resp = api_client.post(
        "/api/v1/admin/service-accounts",
        json={"name": "nope", "role": "producer"},
        headers=api_client.viewer_headers,
    )
    assert resp.status_code == 403


def test_viewer_role_jwt_cannot_create_job(api_client):
    sa = _create_service_account(api_client, name="watcher", role="viewer")
    token = _get_token(api_client, sa["client_id"], sa["client_secret"]).json()[
        "access_token"
    ]
    resp = api_client.post(
        "/api/v1/jobs/",
        json={"name": "x", "estimated_duration": 1, "payload": {"type": "sleep"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_api_keys_still_work_after_jwt_wiring(api_client):
    """Regression guard: JWT-first ordering must not break API-key auth."""
    resp = api_client.get("/api/v1/jobs/", headers=api_client.operator_headers)
    assert resp.status_code == 200
