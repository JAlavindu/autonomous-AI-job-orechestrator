import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.config import settings
from src.db.models import AuditLogRow, DependencyRow, JobRow, RunRow, TenantRow
from src.db.session import SessionLocal
from src.models.job import Job, JobCreate, JobStatus
from src.db.redis_store import redis_client
from src.orchestrator.executors.base import ExecutionResult

class JobManager:
    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory
        # Temporary Phase 1A queue/cache compatibility; durable state is Postgres.
        self.db = redis_client

    def _ensure_default_tenant(self, db: Session) -> TenantRow:
        tenant = db.get(TenantRow, settings.DEFAULT_TENANT_ID)
        if tenant:
            return tenant

        tenant = TenantRow(
            id=settings.DEFAULT_TENANT_ID,
            name=settings.DEFAULT_TENANT_NAME,
        )
        db.add(tenant)
        db.flush()
        return tenant

    def _audit(
        self,
        db: Session,
        action: str,
        target: str,
        payload: dict | None = None,
        actor: str = "system",
    ) -> None:
        db.add(
            AuditLogRow(
                id=str(uuid.uuid4()),
                tenant_id=settings.DEFAULT_TENANT_ID,
                actor=actor,
                action=action,
                target=target,
                payload=payload or {},
            )
        )

    def _dependencies_for_job(self, db: Session, job_id: str) -> list[str]:
        stmt = select(DependencyRow.depends_on_job_id).where(DependencyRow.job_id == job_id)
        return list(db.scalars(stmt).all())

    def _to_model(self, db: Session, row: JobRow) -> Job:
        return Job(
            id=row.id,
            name=row.name,
            description=row.description,
            priority=row.priority,
            deadline=row.deadline,
            estimated_duration=row.est_duration,
            dependencies=self._dependencies_for_job(db, row.id),
            payload=row.payload or {},
            status=JobStatus(row.status),
            created_at=row.created_at,
            started_at=row.started_at,
            completed_at=row.completed_at,
            retry_count=row.retry_count,
            worker_id=row.worker_id,
        )

    def create_job(self, job_create: JobCreate) -> Job:
        """Creates a new job, saves it to the DB, and returns the Job object."""
        job = Job(**job_create.model_dump())

        with self.session_factory() as db:
            try:
                self._ensure_default_tenant(db)
                row = JobRow(
                    id=job.id,
                    tenant_id=settings.DEFAULT_TENANT_ID,
                    name=job.name,
                    description=job.description,
                    priority=job.priority,
                    deadline=job.deadline,
                    est_duration=job.estimated_duration,
                    status=job.status.value if isinstance(job.status, JobStatus) else job.status,
                    payload=job.payload,
                    retry_count=job.retry_count,
                    worker_id=job.worker_id,
                    created_at=job.created_at,
                    started_at=job.started_at,
                    completed_at=job.completed_at,
                )
                db.add(row)
                db.flush()

                for parent_id in job.dependencies:
                    db.add(DependencyRow(job_id=job.id, depends_on_job_id=parent_id))

                self._audit(
                    db,
                    action="job.created",
                    target=f"job:{job.id}",
                    payload={"name": job.name, "dependencies": job.dependencies},
                )
                db.commit()
                db.refresh(row)
                return self._to_model(db, row)
            except Exception:
                db.rollback()
                raise

    def get_job(self, job_id: str) -> Optional[Job]:
        with self.session_factory() as db:
            row = db.get(JobRow, job_id)
            if not row:
                return None
            return self._to_model(db, row)

    def list_jobs(self) -> List[Job]:
        with self.session_factory() as db:
            stmt = select(JobRow).order_by(JobRow.created_at.asc(), JobRow.id.asc())
            return [self._to_model(db, row) for row in db.scalars(stmt).all()]

    def update_job_status(self, job_id: str, status: JobStatus, worker_id: Optional[str] = None) -> Optional[Job]:
        """Updates job status and sets completion time if applicable."""
        with self.session_factory() as db:
            try:
                row = db.get(JobRow, job_id)
                if not row:
                    return None

                previous_status = row.status

                if status == JobStatus.RUNNING and row.status != JobStatus.RUNNING:
                    row.started_at = datetime.utcnow()

                row.status = status.value if isinstance(status, JobStatus) else status

                if worker_id:
                    row.worker_id = worker_id

                if status == JobStatus.COMPLETED:
                    row.completed_at = datetime.utcnow()
                elif status == JobStatus.RETRYING:
                    row.retry_count += 1

                self._audit(
                    db,
                    action="job.status_changed",
                    target=f"job:{job_id}",
                    payload={"from": previous_status, "to": row.status, "worker_id": row.worker_id},
                )
                db.commit()
                db.refresh(row)
                return self._to_model(db, row)
            except Exception:
                db.rollback()
                raise

    def start_run(self, job_id: str, worker_id: str) -> Optional[RunRow]:
        with self.session_factory() as db:
            try:
                job = db.get(JobRow, job_id)
                if not job:
                    return None

                latest_attempt = db.scalar(
                    select(RunRow.attempt)
                    .where(RunRow.job_id == job_id)
                    .order_by(RunRow.attempt.desc())
                    .limit(1)
                )
                attempt = (latest_attempt or 0) + 1
                run = RunRow(
                    id=str(uuid.uuid4()),
                    job_id=job_id,
                    attempt=attempt,
                    worker_id=worker_id,
                    status=JobStatus.RUNNING.value,
                    started_at=datetime.utcnow(),
                )
                db.add(run)
                self._audit(
                    db,
                    action="run.started",
                    target=f"run:{run.id}",
                    payload={"job_id": job_id, "attempt": attempt, "worker_id": worker_id},
                )
                db.commit()
                db.refresh(run)
                return run
            except Exception:
                db.rollback()
                raise

    def finish_run(self, run_id: str, status: JobStatus, result: ExecutionResult) -> None:
        with self.session_factory() as db:
            try:
                run = db.get(RunRow, run_id)
                if not run:
                    return

                run.status = status.value if isinstance(status, JobStatus) else status
                run.finished_at = datetime.utcnow()
                run.exit_code = result.exit_code
                run.error = result.error_message
                run.stdout = result.stdout
                run.stderr = result.stderr
                run.metrics = {"duration_seconds": result.duration_seconds}
                self._audit(
                    db,
                    action="run.finished",
                    target=f"run:{run.id}",
                    payload={
                        "job_id": run.job_id,
                        "attempt": run.attempt,
                        "status": run.status,
                        "exit_code": run.exit_code,
                    },
                )
                db.commit()
            except Exception:
                db.rollback()
                raise

    def are_dependencies_met(self, job: Job) -> bool:
        """Returns True if all parent jobs (dependencies) are COMPLETED."""
        if not job.dependencies:
            return True

        for parent_id in job.dependencies:
            parent_job = self.get_job(parent_id)
            #If parent doesn't exist or isn't complete, dependency is not met
            if not parent_job or parent_job.status != JobStatus.COMPLETED:
                return False
        
        return True

job_manager = JobManager()
