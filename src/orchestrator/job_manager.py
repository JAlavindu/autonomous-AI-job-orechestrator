from typing import List, Optional
from datetime import datetime
from src.models.job import Job, JobCreate, JobStatus
from src.db.redis_store import redis_client

class JobManager:
    def __init__(self):
        self.db = redis_client

    def create_job(self, job_id: str, status: JobStatus, worker_id: Optional[str] = None) -> Optional[Job]:
        """Create & update a job, sets completion time if applicable, saves it to the DB, and returns the Job object."""
        job = self.get_job(job_id)
        if not job:
            return None

        # Capture start time when transitioning to RUNNING
        if status == JobStatus.RUNNING and job.status != JobStatus.RUNNING:
            job.started_at = datetime.utcnow()

        job.status = status
        
        if worker_id:
            job.worker_id = worker_id

        if status == JobStatus.COMPLETED:
            job.completed_at = datetime.utcnow()
        elif status == JobStatus.RETRYING:
            job.retry_count += 1
        elif status == JobStatus.FAILED:
            # Maybe reset worker_id so it's clear no one is working on it
            pass
        
        self.db.save_job(job)
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        return self.db.get_job(job_id)

    def list_jobs(self) -> List[Job]:
        return self.db.get_all_jobs()

    def update_job_status(self, job_id: str, status: JobStatus, worker_id: Optional[str] = None) -> Optional[Job]:
        """Updates job status and sets completion time if applicable."""
        job = self.get_job(job_id)
        if not job:
            return None

        job.status = status
        
        if worker_id:
            job.worker_id = worker_id

        if status == JobStatus.COMPLETED:
            job.completed_at = datetime.utcnow()
        elif status == JobStatus.RETRYING:
            job.retry_count += 1
        
        self.db.save_job(job)
        return job

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