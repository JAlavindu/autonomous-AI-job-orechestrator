from fastapi import APIRouter, HTTPException, status
from typing import List
from src.models.job import Job, JobCreate
from src.orchestrator.job_manager import job_manager

router = APIRouter()

@router.post("/jobs/", response_model=Job, status_code=status.HTTP_201_CREATED)
def create_job(job_create: JobCreate):
    """
    Create a new job with the specified parameters.
    """
    try:
        job = job_manager.create_job(job_create)
        return job
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/jobs/", response_model=List[Job])
def list_jobs():
    """
    Retrieve a list of all jobs in the system.
    """
    return job_manager.list_jobs()

@router.get("/jobs/{job_id}", response_model=Job)
def get_job(job_id: str):
    """
    Retrieve a specific job by its ID.
    """
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job