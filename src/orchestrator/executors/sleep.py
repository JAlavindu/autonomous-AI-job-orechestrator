import time
from src.models.job import Job
from src.orchestrator.executors.base import BaseExecutor, ExecutionResult

class SleepExecutor(BaseExecutor):
    def execute(self, job: Job) -> ExecutionResult:
        duration = job.estimated_duration if job.estimated_duration > 0 else 1.0
        start = time.time()
        time.sleep(duration)
        return ExecutionResult(
            success=True,
            exit_code=0,
            stdout=f"Slept for {duration} seconds",
            duration_seconds=time.time() - start,
        )