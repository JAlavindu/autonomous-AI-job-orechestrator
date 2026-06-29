from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


class DependencyRow(Base):
    __tablename__ = "dependencies"

    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), primary_key=True)
    depends_on_job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), primary_key=True)

    job = relationship("JobRow", foreign_keys=[job_id], back_populates="dependencies")
    depends_on_job = relationship("JobRow", foreign_keys=[depends_on_job_id])

    __table_args__ = (
        UniqueConstraint("job_id", "depends_on_job_id", name="uq_dependencies_edge"),
    )
