from fastapi import APIRouter, HTTPException, status
from typing import List

from src.core.logging_config import get_logger
from src.models.job import Job, JobCreate
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


@router.get("/jobs/", response_model=List[Job])
def list_jobs():
    return job_manager.list_jobs()


@router.get("/jobs/{job_id}", response_model=Job)
def get_job(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
