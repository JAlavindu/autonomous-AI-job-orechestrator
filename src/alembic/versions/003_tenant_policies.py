"""tenant policy columns for phase 2 step 2

Revision ID: 003_tenant_policies
Revises: 002_api_keys
Create Date: 2026-07-04 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "003_tenant_policies"
down_revision: str | None = "002_api_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.add_column("tenants", sa.Column("max_jobs", sa.Integer(), nullable=True))
    op.add_column("tenants", sa.Column("executor_allowlist", sa.Text(), nullable=True))

    op.execute(
        sa.text(
            "UPDATE tenants SET max_jobs = 1000, rate_limit = COALESCE(rate_limit, 120), "
            "executor_allowlist = 'sleep' WHERE id = :id"
        ).bindparams(id=DEFAULT_TENANT_ID)
    )


def downgrade() -> None:
    op.drop_column("tenants", "executor_allowlist")
    op.drop_column("tenants", "max_jobs")