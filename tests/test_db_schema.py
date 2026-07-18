import pytest
from sqlalchemy import inspect, text, create_engine

from src.core.config import settings
from src.db.session import get_engine


def _postgres_available() -> bool:
    try:
        engine = create_engine(settings.DATABASE_URL)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        try:
            engine.dispose()
        except UnboundLocalError:
            pass


pytestmark = pytest.mark.skipif(
    not _postgres_available(),
    reason="requires a running Postgres at DATABASE_URL",
)

def _uses_postgres() -> bool:
    return get_engine().dialect.name == "postgresql"


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