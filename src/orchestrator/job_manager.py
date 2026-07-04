import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.output import truncate_output
from src.db.models import AuditLogRow, DependencyRow, JobRow, RunRow, TenantRow
from src.db.session import SessionLocal
from src.db.redis_store import redis_client
from src.db.stream_queue import job_stream
from src.models.job import DagJobCreate, Job, JobCreate, JobStatus, Run
from src.orchestrator.executors.base import ExecutionResult
from src.storage.run_logs import load_full_run_logs, persist_run_output


class JobManager:
    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory
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
            idempotency_key=row.idempotency_key,
        )

    def _run_to_model(self, row: RunRow) -> Run:
        return Run(
            id=row.id,
            job_id=row.job_id,
            attempt=row.attempt,
            worker_id=row.worker_id,
            status=row.status,
            started_at=row.started_at,
            finished_at=row.finished_at,
            exit_code=row.exit_code,
            error=row.error,
            stdout=row.stdout,
            stderr=row.stderr,
            metrics=row.metrics,
            log_ref=row.log_ref if row.log_ref else None,
        )

    def _retry_backoff_seconds(self, retry_count: int) -> float:
        delay = settings.RETRY_BACKOFF_BASE_SECONDS * (2 ** max(retry_count, 0))
        return min(delay, settings.RETRY_BACKOFF_MAX_SECONDS)

    def create_job(self, job_create: JobCreate) -> Job:
        job = Job(**job_create.model_dump())

        with self.session_factory() as db:
            try:
                self._ensure_default_tenant(db)

                if job.idempotency_key:
                    existing = db.scalar(
                        select(JobRow).where(
                            JobRow.tenant_id == settings.DEFAULT_TENANT_ID,
                            JobRow.idempotency_key == job.idempotency_key,
                        )
                    )
                    if existing:
                        return self._to_model(db, existing)

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
                    idempotency_key=job.idempotency_key,
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
                    payload={
                        "name": job.name,
                        "dependencies": job.dependencies,
                        "idempotency_key": job.idempotency_key,
                    },
                )
                db.commit()
                db.refresh(row)
                created = self._to_model(db, row)
                if job_create.enqueue and self.are_dependencies_met(created):
                    self.enqueue_job(created.id)
                return created
            except IntegrityError:
                db.rollback()
                if job.idempotency_key:
                    with self.session_factory() as retry_db:
                        existing = retry_db.scalar(
                            select(JobRow).where(
                                JobRow.tenant_id == settings.DEFAULT_TENANT_ID,
                                JobRow.idempotency_key == job.idempotency_key,
                            )
                        )
                        if existing:
                            return self._to_model(retry_db, existing)
                raise
            except Exception:
                db.rollback()
                raise

    def create_dag(self, nodes: List[DagJobCreate]) -> List[Job]:
        keys = [node.key for node in nodes]
        if len(keys) != len(set(keys)):
            raise ValueError("DAG job keys must be unique")

        known_keys = set(keys)
        for node in nodes:
            for dep in node.depends_on:
                if dep not in known_keys:
                    raise ValueError(f"Unknown dependency key '{dep}' in DAG")

        with self.session_factory() as db:
            try:
                self._ensure_default_tenant(db)
                key_to_id: dict[str, str] = {}
                rows: list[tuple[DagJobCreate, JobRow]] = []

                for node in nodes:
                    job_id = str(uuid.uuid4())
                    key_to_id[node.key] = job_id
                    row = JobRow(
                        id=job_id,
                        tenant_id=settings.DEFAULT_TENANT_ID,
                        name=node.name,
                        description=node.description,
                        priority=node.priority,
                        deadline=node.deadline,
                        est_duration=node.estimated_duration,
                        status=JobStatus.PENDING.value,
                        payload=node.payload or {},
                        retry_count=0,
                    )
                    db.add(row)
                    rows.append((node, row))

                db.flush()

                for node, row in rows:
                    for dep_key in node.depends_on:
                        db.add(
                            DependencyRow(
                                job_id=row.id,
                                depends_on_job_id=key_to_id[dep_key],
                            )
                        )

                self._audit(
                    db,
                    action="dag.created",
                    target="dag:batch",
                    payload={"job_keys": keys},
                )
                db.commit()

                return [self._to_model(db, row) for _, row in rows]
            except Exception:
                db.rollback()
                raise

    def get_job(self, job_id: str) -> Optional[Job]:
        with self.session_factory() as db:
            row = db.get(JobRow, job_id)
            if not row:
                return None
            return self._to_model(db, row)

    def list_jobs(
        self,
        status: JobStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Job], int]:
        with self.session_factory() as db:
            stmt = select(JobRow)
            count_stmt = select(func.count()).select_from(JobRow)

            if status is not None:
                status_value = status.value if isinstance(status, JobStatus) else status
                stmt = stmt.where(JobRow.status == status_value)
                count_stmt = count_stmt.where(JobRow.status == status_value)

            total = db.scalar(count_stmt) or 0
            stmt = stmt.order_by(JobRow.created_at.asc(), JobRow.id.asc()).limit(limit).offset(offset)
            jobs = [self._to_model(db, row) for row in db.scalars(stmt).all()]
            return jobs, int(total)

    def get_runs(self, job_id: str) -> Tuple[List[Run], int]:
        with self.session_factory() as db:
            stmt = (
                select(RunRow)
                .where(RunRow.job_id == job_id)
                .order_by(RunRow.attempt.asc())
            )
            rows = list(db.scalars(stmt).all())
            return [self._run_to_model(row) for row in rows], len(rows)

    def get_run(self, job_id: str, run_id: str) -> Optional[Run]:
        with self.session_factory() as db:
            row = db.get(RunRow, run_id)
            if not row or row.job_id != job_id:
                return None
            return self._run_to_model(row)

    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        worker_id: Optional[str] = None,
    ) -> Optional[Job]:
        with self.session_factory() as db:
            try:
                row = db.get(JobRow, job_id)
                if not row:
                    return None

                previous_status = row.status

                if status == JobStatus.RUNNING and row.status != JobStatus.RUNNING.value:
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

    def cancel_job(self, job_id: str, actor: str = "api") -> Optional[Job]:
        with self.session_factory() as db:
            try:
                row = db.get(JobRow, job_id)
                if not row:
                    return None

                if row.status in {
                    JobStatus.COMPLETED.value,
                    JobStatus.FAILED.value,
                    JobStatus.CANCELLED.value,
                }:
                    raise ValueError(f"Job {job_id} cannot be cancelled from status {row.status}")

                previous_status = row.status
                row.status = JobStatus.CANCELLED.value
                row.completed_at = datetime.utcnow()

                self._audit(
                    db,
                    action="job.cancelled",
                    target=f"job:{job_id}",
                    payload={"from": previous_status},
                    actor=actor,
                )
                db.commit()
                db.refresh(row)
                return self._to_model(db, row)
            except Exception:
                db.rollback()
                raise

    def retry_job(self, job_id: str, actor: str = "api") -> Optional[Job]:
        job = self.get_job(job_id)
        if not job:
            return None

        if job.status not in {JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.RETRYING}:
            raise ValueError(f"Job {job_id} cannot be retried from status {job.status}")

        if not self.are_dependencies_met(job):
            raise ValueError(f"Job {job_id} dependencies are not met")

        updated = self.update_job_status(job_id, JobStatus.PENDING)
        self._audit_manual(job_id, "job.manual_retry", actor)
        self.enqueue_job(job_id)
        return updated

    def _audit_manual(self, job_id: str, action: str, actor: str) -> None:
        with self.session_factory() as db:
            self._audit(db, action=action, target=f"job:{job_id}", actor=actor)
            db.commit()

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

                persisted = persist_run_output(
                    run_id=run_id,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    error=result.error_message,
                )

                run.status = status.value if isinstance(status, JobStatus) else status
                run.finished_at = datetime.utcnow()
                run.exit_code = result.exit_code
                run.error = persisted.error
                run.stdout = persisted.stdout
                run.stderr = persisted.stderr
                run.log_ref = persisted.log_ref
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
                        "log_ref": run.log_ref,
                    },
                )
                db.commit()
            except Exception:
                db.rollback()
                raise

    def handle_execution_failure(
        self,
        job_id: str,
        run_id: str,
        result: ExecutionResult,
        source_message_id: str | None = None,
    ) -> tuple[str, float]:
        """
        Decide retry vs terminal failure vs DLQ.
        Returns (action, delay_seconds) where action is 'retry', 'failed', or 'dlq'.
        """
        self.finish_run(run_id, JobStatus.FAILED, result)

        job = self.get_job(job_id)
        if not job:
            return "failed", 0.0

        if job.retry_count < settings.MAX_JOB_RETRIES:
            delay = self._retry_backoff_seconds(job.retry_count)
            self.update_job_status(job_id, JobStatus.RETRYING)
            self._audit_manual(job_id, "job.retry_scheduled", "worker")
            return "retry", delay

        self.update_job_status(job_id, JobStatus.FAILED)
        reason = result.error_message or f"exit_code={result.exit_code}"
        job_stream.send_to_dlq(job_id, reason=reason, source_message_id=source_message_id)
        self._audit_manual(job_id, "job.dlq", "worker")
        return "dlq", 0.0

    def are_dependencies_met(self, job: Job) -> bool:
        if not job.dependencies:
            return True

        for parent_id in job.dependencies:
            parent_job = self.get_job(parent_id)
            if not parent_job or parent_job.status != JobStatus.COMPLETED:
                return False

        return True

    def enqueue_job(self, job_id: str) -> str:
        return job_stream.enqueue(job_id)
    
        def get_run_logs(self, job_id: str, run_id: str, full: bool = False) -> Optional[dict]:
            with self.session_factory() as db:
                row = db.get(RunRow, run_id)
                if not row or row.job_id != job_id:
                    return None

                if not full:
                    return {
                        "run_id": row.id,
                        "job_id": row.job_id,
                        "stdout": row.stdout,
                        "stderr": row.stderr,
                        "error": row.error,
                        "stdout_ref": None,
                        "stderr_ref": None,
                        "error_ref": None,
                        "spilled": bool(row.log_ref),
                    }

            merged = load_full_run_logs(row.log_ref, row.stdout, row.stderr, row.error)
            merged["run_id"] = row.id
            merged["job_id"] = row.job_id
            return merged

    def list_dlq(self, limit: int = 100) -> list[dict]:
        return job_stream.list_dlq(count=limit)


job_manager = JobManager()