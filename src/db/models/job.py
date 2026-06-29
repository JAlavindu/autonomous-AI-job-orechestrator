from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from src.db.base import Base

JSONType = JSON().with_variant(JSONB, "postgresql")


class JobRow(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, default=1)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    est_duration: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    schedule_id: Mapped[str | None] = mapped_column(ForeignKey("schedules.id"))
    idempotency_key: Mapped[str | None] = mapped_column(String(255))
    payload: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    resource_req: Mapped[dict | None] = mapped_column(JSONType)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    worker_id: Mapped[str | None] = mapped_column(String(128))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    tenant = relationship("TenantRow", back_populates="jobs")
    schedule = relationship("ScheduleRow", back_populates="jobs")
    runs = relationship("RunRow", back_populates="job", cascade="all, delete-orphan")
    dependencies = relationship(
        "DependencyRow",
        foreign_keys="DependencyRow.job_id",
        back_populates="job",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_jobs_tenant_idempotency_key"),
        Index("ix_jobs_tenant_status", "tenant_id", "status"),
        Index("ix_jobs_schedule_id", "schedule_id"),
    )
