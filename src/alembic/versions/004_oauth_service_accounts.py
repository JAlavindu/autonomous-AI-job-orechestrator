"""phase 2 step 3 oauth service accounts

Revision ID: 004_oauth_service_accounts
Revises: 003_tenant_policies
"""

from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "004_oauth_service_accounts"
down_revision: str | None = "003_tenant_policies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "service_accounts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("secret_hash", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id"),
        sa.UniqueConstraint("secret_hash"),
    )
    op.create_index("ix_service_accounts_tenant_id", "service_accounts", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_service_accounts_tenant_id", table_name="service_accounts")
    op.drop_table("service_accounts")