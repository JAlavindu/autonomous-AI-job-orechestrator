from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from src.db.base import Base

JSONType = JSON().with_variant(JSONB, "postgresql")


class RunRow(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False, index=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    worker_id: Mapped[str] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_code: Mapped[int] = mapped_column(Integer, nullable=True)
    error: Mapped[str] = mapped_column(Text, nullable=True)
    stdout: Mapped[str] = mapped_column(Text, nullable=True)
    stderr: Mapped[str] = mapped_column(Text, nullable=True)
    log_ref: Mapped[str] = mapped_column(String(512), nullable=True)
    metrics: Mapped[dict] = mapped_column(JSONType, nullable=True)

    job = relationship("JobRow", back_populates="runs")

    __table_args__ = (UniqueConstraint("job_id", "attempt", name="uq_runs_job_attempt"),)
