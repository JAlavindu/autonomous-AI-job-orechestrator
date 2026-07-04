from fastapi import APIRouter, HTTPException, Query, status
from typing import Optional

from src.core.logging_config import get_logger
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


@router.post("/jobs/", response_model=Job, status_code=status.HTTP_201_CREATED)
def create_job(job_create: JobCreate):
    try:
        job = job_manager.create_job(job_create)
        logger.info("Created job %s (%s)", job.name, job.id)
        return job
    except Exception as e:
        logger.exception("Failed to create job: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/jobs/dag", response_model=DagSubmitResponse, status_code=status.HTTP_201_CREATED)
def submit_dag(body: DagSubmit):
    try:
        jobs = job_manager.create_dag(body.jobs)
        logger.info("Created DAG with %s jobs", len(jobs))
        return DagSubmitResponse(jobs=jobs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to create DAG: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/", response_model=JobListResponse)
def list_jobs(
    status_filter: Optional[JobStatus] = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    items, total = job_manager.list_jobs(status=status_filter, limit=limit, offset=offset)
    return JobListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/jobs/{job_id}", response_model=Job)
def get_job(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/jobs/{job_id}/cancel", response_model=Job)
def cancel_job(job_id: str):
    try:
        job = job_manager.cancel_job(job_id, actor="api")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    logger.info("Cancelled job %s", job_id)
    return job


@router.post("/jobs/{job_id}/retry", response_model=Job)
def retry_job(job_id: str):
    try:
        job = job_manager.retry_job(job_id, actor="api")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    logger.info("Manual retry requested for job %s", job_id)
    return job


@router.get("/jobs/{job_id}/runs", response_model=RunListResponse)
def list_runs(job_id: str):
    if not job_manager.get_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    items, total = job_manager.get_runs(job_id)
    return RunListResponse(items=items, total=total)


@router.get("/jobs/{job_id}/runs/{run_id}", response_model=Run)
def get_run(job_id: str, run_id: str):
    run = job_manager.get_run(job_id, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/jobs/{job_id}/runs/{run_id}/logs", response_model=RunLogsResponse)
def get_run_logs(
    job_id: str,
    run_id: str,
    full: bool = Query(default=False, description="Load full spilled logs from object storage"),
):
    logs = job_manager.get_run_logs(job_id, run_id, full=full)
    if not logs:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunLogsResponse(**logs)


@router.get("/dlq", response_model=DlqListResponse)
def list_dlq(limit: int = Query(default=100, ge=1, le=1000)):
    items = job_manager.list_dlq(limit=limit)
    return DlqListResponse(items=items, total=len(items))