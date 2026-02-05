import asyncio
import traceback
from src.models.job import Job, JobStatus
from src.orchestrator.job_manager import job_manager

class JobExecutor:
    """
    Responsible for executing jobs.
    In a real system, this might dispatch to Docker, Kubernetes, or separate worker processes.
    Here, we simulate execution using asyncio.
    """

    async def execute_job(self, job: Job):
        """
        Executes a single job asynchronously.
        """
        print(f"[*] Starting execution of Job {job.name} ({job.id})")
        
        # 1. Update status to RUNNING
        job_manager.update_job_status(job.id, JobStatus.RUNNING, worker_id="local-worker-1")

        try:
            # 2. Simulate the workload duration
            # In a real scenario, this is where the actual computation happens
            duration = job.estimated_duration
            if duration <= 0:
                duration = 1  # Ensure at least some execution time
            
            await asyncio.sleep(duration)

            # 3. Update status to COMPLETED
            job_manager.update_job_status(job.id, JobStatus.COMPLETED)
            print(f"[+] Job {job.name} ({job.id}) COMPLETED successfully.")

        except Exception as e:
            # 4. Handle failures
            print(f"[-] Job {job.name} ({job.id}) FAILED: {str(e)}")
            traceback.print_exc()
            job_manager.update_job_status(job.id, JobStatus.FAILED)

# Global executor instance
executor = JobExecutor()