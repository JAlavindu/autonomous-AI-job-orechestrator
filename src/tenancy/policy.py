from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.core.config import settings
from src.db.models import JobRow, TenantRow
from src.db.session import SessionLocal
from src.tenancy.exceptions import QuotaExceededError

ACTIVE_JOB_STATUSES = ("PENDING", "RUNNING", "RETRYING", "QUEUED")


class TenantPolicyService:
    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory

    def get_tenant(self, db: Session, tenant_id: str) -> TenantRow | None:
        return db.get(TenantRow, tenant_id)

    def max_jobs_for(self, tenant: TenantRow | None) -> int:
        if tenant and tenant.max_jobs is not None:
            return tenant.max_jobs
        return settings.DEFAULT_TENANT_MAX_JOBS

    def rate_limit_for(self, tenant: TenantRow | None) -> int:
        if tenant and tenant.rate_limit is not None:
            return tenant.rate_limit
        return settings.DEFAULT_TENANT_RATE_LIMIT

    def executor_allowlist_for(self, tenant: TenantRow | None) -> set[str]:
        raw = None
        if tenant and tenant.executor_allowlist:
            raw = tenant.executor_allowlist
        if not raw:
            return settings.executor_allowlist
        return {e.strip() for e in raw.split(",") if e.strip()}

    def enforce_job_quota(self, db: Session, tenant_id: str, additional: int = 1) -> None:
        tenant = self.get_tenant(db, tenant_id)
        max_jobs = self.max_jobs_for(tenant)
        active = db.scalar(
            select(func.count())
            .select_from(JobRow)
            .where(
                JobRow.tenant_id == tenant_id,
                JobRow.status.in_(ACTIVE_JOB_STATUSES),
            )
        ) or 0
        if active + additional > max_jobs:
            raise QuotaExceededError(
                f"Tenant {tenant_id} job quota exceeded ({active}/{max_jobs} active)"
            )

    def validate_executor_type(self, tenant_id: str, executor_type: str) -> None:
        with self.session_factory() as db:
            tenant = self.get_tenant(db, tenant_id)
            allowlist = self.executor_allowlist_for(tenant)
        if executor_type not in allowlist:
            raise ValueError(
                f"Executor '{executor_type}' is not allowed for tenant (allowed: {sorted(allowlist)})"
            )


tenant_policy = TenantPolicyService()