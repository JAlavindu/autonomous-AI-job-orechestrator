import asyncio
import time
from src.db.redis_store import redis_client
from src.orchestrator.job_manager import job_manager
from src.models.job import JobStatus

def run_worker(worker_id: str):
    print(f"[*] Worker {worker_id} started. Waiting for jobs...")
    
    while True:
        try:
            # 1. Blocking wait for a job ID
            job_id = redis_client.pop_from_queue()
            
            if not job_id:
                continue

            # 2. Fetch Job Details
            job = job_manager.get_job(job_id)
            if not job:
                print(f"[!] Worker received invalid job ID: {job_id}")
                continue

            print(f"[{worker_id}] Processing Job: {job.name}")
            
            # 3. Update Status to RUNNING
            job_manager.update_job_status(job_id, JobStatus.RUNNING, worker_id=worker_id)
            
            # 4. Simulate Work (Sleep)
            # In real life, this is where Docker/K8s logic goes
            duration = job.estimated_duration
            match_work = duration if duration > 0 else 1
            time.sleep(match_work)
            
            # 5. Update Status to COMPLETED
            job_manager.update_job_status(job_id, JobStatus.COMPLETED)
            print(f"[{worker_id}] Finished Job: {job.name}")

        except Exception as e:
            print(f"[!] Worker Error: {e}")
            time.sleep(2)

if __name__ == "__main__":
    import sys
    # Allow running multiple workers with different IDs
    w_id = sys.argv[1] if len(sys.argv) > 1 else "worker-1"
    run_worker(w_id)