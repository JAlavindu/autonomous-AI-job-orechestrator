import asyncio
import traceback
from typing import List
from src.models.job import Job, JobStatus
from src.orchestrator.job_manager import job_manager
from src.orchestrator.executor import executor

class Scheduler:
    def __init__(self, check_interval: float = 2.0):
        self.check_interval = check_interval
        self.is_running = False

    async def run(self):
        """
        Main loop of the scheduler.
        Continuously checks for pending jobs and schedules them.
        """
        self.is_running = True
        print("[*] Scheduler started. Waiting for jobs...")

        while self.is_running:
            try:
                # 1. Get all jobs that are PENDING
                all_jobs = job_manager.list_jobs()
                pending_jobs = [j for j in all_jobs if j.status == JobStatus.PENDING]

                for job in pending_jobs:
                    # 2. Check if dependencies are met
                    if job_manager.are_dependencies_met(job):
                        # 3. Dispatch to executor (Fire and Forget)
                        print(f"[>] Scheduling Job: {job.name}")
                        asyncio.create_task(executor.execute_job(job))
                    else:
                        # Debug info (optional)
                        # print(f"[-] Job {job.name} waiting for dependencies.")
                        pass

                # 4. Wait before next cycle to prevent high CPU usage
                await asyncio.sleep(self.check_interval)

            except Exception as e:
                print(f"[!] Scheduler loop error: {e}")
                traceback.print_exc()
                await asyncio.sleep(5)  # Wait longer on error before retrying

    def stop(self):
        self.is_running = False
        print("[*] Scheduler stopping...")

# Global scheduler instance
scheduler = Scheduler()