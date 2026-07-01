import pytest
from sqlalchemy import inspect, text

from src.core.config import settings
from src.db.session import get_engine


def _uses_postgres() -> bool:
    return get_engine().dialect.name == "postgresql"led


@pytest.mark.skipif(not _uses_postgres(), reason="Requires Postgres DATABASE_URL")
def test_all_phase1_tables_exist():
    inspector = inspect(get_engine())
    tables = set(inspector.get_table_names())
    for name in ["tenants", "jobs", "runs", "dependencies", "schedules", "audit_log"]:
        assert name in tables


@pytest.mark.skipif(not _uses_postgres(), reason="Requires Postgres DATABASE_URL")
def test_default_tenant_exists():
    with get_engine().connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM tenants WHERE id = :id"),
            {"id": settings.DEFAULT_TENANT_ID},
        ).scalar_one()
    assert count == 1