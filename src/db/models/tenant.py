from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


class TenantRow(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    quota_cpu: Mapped[int] = mapped_column(Integer, nullable=True)
    quota_mem: Mapped[int] = mapped_column(Integer, nullable=True)
    rate_limit: Mapped[int] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    jobs = relationship("JobRow", back_populates="tenant")
    schedules = relationship("ScheduleRow", back_populates="tenant")
