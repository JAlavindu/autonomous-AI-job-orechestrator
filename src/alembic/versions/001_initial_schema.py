"""initial phase 1 schema

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-06-30 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_TENANT_NAME = "default"

JSONType = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("quota_cpu", sa.Integer(), nullable=True),
        sa.Column("quota_mem", sa.Integer(), nullable=True),
        sa.Column("rate_limit", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "schedules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("cron", sa.String(length=255), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_schedules_tenant_id", "schedules", ["tenant_id"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("est_duration", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("schedule_id", sa.String(length=36), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("payload", JSONType, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("resource_req", JSONType, nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["schedule_id"], ["schedules.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_jobs_tenant_idempotency_key"),
    )
    op.create_index("ix_jobs_schedule_id", "jobs", ["schedule_id"])
    op.create_index("ix_jobs_tenant_status", "jobs", ["tenant_id", "status"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=False, server_default="system"),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("target", sa.String(length=255), nullable=False),
        sa.Column("payload", JSONType, nullable=True),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_tenant_id", "audit_log", ["tenant_id"])

    op.create_table(
        "dependencies",
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("depends_on_job_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["depends_on_job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.PrimaryKeyConstraint("job_id", "depends_on_job_id"),
        sa.UniqueConstraint("job_id", "depends_on_job_id", name="uq_dependencies_edge"),
    )

    op.create_table(
        "runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("stdout", sa.Text(), nullable=True),
        sa.Column("stderr", sa.Text(), nullable=True),
        sa.Column("log_ref", sa.String(length=512), nullable=True),
        sa.Column("metrics", JSONType, nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "attempt", name="uq_runs_job_attempt"),
    )
    op.create_index("ix_runs_job_id", "runs", ["job_id"])

    op.execute(
    sa.text(
        "INSERT INTO tenants (id, name, created_at) "
        "VALUES (:id, :name, NOW()) "
        "ON CONFLICT (id) DO NOTHING"
    ).bindparams(id=DEFAULT_TENANT_ID, name=DEFAULT_TENANT_NAME)
)


def downgrade() -> None:
    op.execute(
    sa.text("DELETE FROM tenants WHERE id = :id").bindparams(id=DEFAULT_TENANT_ID)
)
    op.drop_index("ix_runs_job_id", table_name="runs")
    op.drop_table("runs")
    op.drop_table("dependencies")
    op.drop_index("ix_audit_log_tenant_id", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("ix_jobs_tenant_status", table_name="jobs")
    op.drop_index("ix_jobs_schedule_id", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("ix_schedules_tenant_id", table_name="schedules")
    op.drop_table("schedules")
    op.drop_table("tenants")