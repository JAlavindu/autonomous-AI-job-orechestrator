from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.auth.deps import get_current_principal, require_min_role
from src.core.logging_config import get_logger
from src.models.auth import Principal, Role
from src.models.job import (
    DagSubmit,
    DagSubmitResponse,
    DlqListResponse,
    Job,
    JobCreate,
    JobListResponse,
    JobStatus,
    Run,
    RunListResponse,
    RunLogsResponse,
)
from src.orchestrator.job_manager import job_manager

router = APIRouter()
logger = get_logger(__name__)


@router.post(
    "/jobs/",
    response_model=Job,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_min_role(Role.PRODUCER))],
)
def create_job(job_create: JobCreate, principal: Principal = Depends(get_current_principal)):
    try:
        job = job_manager.create_job(job_create)
        logger.info("Created job %s (%s) by %s", job.name, job.id, principal.name)
        return job
    except Exception as e:
        logger.exception("Failed to create job: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/jobs/dag",
    response_model=DagSubmitResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_min_role(Role.PRODUCER))],
)
def submit_dag(body: DagSubmit, principal: Principal = Depends(get_current_principal)):
    try:
        jobs = job_manager.create_dag(body.jobs)
        logger.info("Created DAG with %s jobs by %s", len(jobs), principal.name)
        return DagSubmitResponse(jobs=jobs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to create DAG: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/jobs/",
    response_model=JobListResponse,
    dependencies=[Depends(require_min_role(Role.VIEWER))],
)
def list_jobs(
    status_filter: Optional[JobStatus] = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    items, total = job_manager.list_jobs(status=status_filter, limit=limit, offset=offset)
    return JobListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/jobs/{job_id}",
    response_model=Job,
    dependencies=[Depends(require_min_role(Role.VIEWER))],
)
def get_job(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=Job,
    dependencies=[Depends(require_min_role(Role.PRODUCER))],
)
def cancel_job(job_id: str, principal: Principal = Depends(get_current_principal)):
    try:
        job = job_manager.cancel_job(job_id, actor=f"api:{principal.name}")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    logger.info("Cancelled job %s by %s", job_id, principal.name)
    return job


@router.post(
    "/jobs/{job_id}/retry",
    response_model=Job,
    dependencies=[Depends(require_min_role(Role.PRODUCER))],
)
def retry_job(job_id: str, principal: Principal = Depends(get_current_principal)):
    try:
        job = job_manager.retry_job(job_id, actor=f"api:{principal.name}")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    logger.info("Manual retry for job %s by %s", job_id, principal.name)
    return job


@router.get(
    "/jobs/{job_id}/runs",
    response_model=RunListResponse,
    dependencies=[Depends(require_min_role(Role.VIEWER))],
)
def list_runs(job_id: str):
    if not job_manager.get_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    items, total = job_manager.get_runs(job_id)
    return RunListResponse(items=items, total=total)


@router.get(
    "/jobs/{job_id}/runs/{run_id}",
    response_model=Run,
    dependencies=[Depends(require_min_role(Role.VIEWER))],
)
def get_run(job_id: str, run_id: str):
    run = job_manager.get_run(job_id, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get(
    "/jobs/{job_id}/runs/{run_id}/logs",
    response_model=RunLogsResponse,
    dependencies=[Depends(require_min_role(Role.VIEWER))],
)
def get_run_logs(
    job_id: str,
    run_id: str,
    full: bool = Query(default=False, description="Load full spilled logs from object storage"),
):
    logs = job_manager.get_run_logs(job_id, run_id, full=full)
    if not logs:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunLogsResponse(**logs)


@router.get(
    "/dlq",
    response_model=DlqListResponse,
    dependencies=[Depends(require_min_role(Role.OPERATOR))],
)
def list_dlq(limit: int = Query(default=100, ge=1, le=1000)):
    items = job_manager.list_dlq(limit=limit)
    return DlqListResponse(items=items, total=len(items))