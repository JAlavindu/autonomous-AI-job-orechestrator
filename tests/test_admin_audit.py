from sqlalchemy import select

from src.db.models import AuditLogRow


def _audit_rows(api_client, action):
    with api_client.session_factory() as db:
        return list(db.scalars(select(AuditLogRow).where(AuditLogRow.action == action)))


def test_api_key_create_is_audited(api_client):
    resp = api_client.post(
        "/api/v1/admin/api-keys",
        json={"name": "audited-key", "role": "producer"},
        headers=api_client.operator_headers,
    )
    assert resp.status_code == 201
    # Filter out the fixture's own key-creation entries (actor="system").
    rows = [r for r in _audit_rows(api_client, "api_key.create") if r.actor == "api:test-operator"]
    assert len(rows) == 1
    row = rows[0]
    assert row.actor == "api:test-operator"
    assert row.target == f"api_key:{resp.json()['id']}"
    assert row.payload["name"] == "audited-key"
    # The audit log must never contain the raw secret.
    assert resp.json()["api_key"] not in str(row.payload)


def test_api_key_revoke_is_audited(api_client):
    created = api_client.post(
        "/api/v1/admin/api-keys",
        json={"name": "doomed-key", "role": "viewer"},
        headers=api_client.operator_headers,
    ).json()
    resp = api_client.delete(
        f"/api/v1/admin/api-keys/{created['id']}",
        headers=api_client.operator_headers,
    )
    assert resp.status_code == 204
    rows = _audit_rows(api_client, "api_key.revoke")
    assert len(rows) == 1
    assert rows[0].target == f"api_key:{created['id']}"
    assert rows[0].actor == "api:test-operator"


def test_service_account_create_and_revoke_are_audited(api_client):
    created = api_client.post(
        "/api/v1/admin/service-accounts",
        json={"name": "audited-sa", "role": "producer"},
        headers=api_client.operator_headers,
    ).json()

    create_rows = _audit_rows(api_client, "service_account.create")
    assert len(create_rows) == 1
    assert create_rows[0].target == f"service_account:{created['id']}"
    assert create_rows[0].payload["client_id"] == created["client_id"]
    assert created["client_secret"] not in str(create_rows[0].payload)

    resp = api_client.delete(
        f"/api/v1/admin/service-accounts/{created['id']}",
        headers=api_client.operator_headers,
    )
    assert resp.status_code == 204
    revoke_rows = _audit_rows(api_client, "service_account.revoke")
    assert len(revoke_rows) == 1
    assert revoke_rows[0].actor == "api:test-operator"


def test_failed_revoke_leaves_no_audit_entry(api_client):
    resp = api_client.delete(
        "/api/v1/admin/api-keys/nonexistent-id",
        headers=api_client.operator_headers,
    )
    assert resp.status_code == 404
    assert _audit_rows(api_client, "api_key.revoke") == []
