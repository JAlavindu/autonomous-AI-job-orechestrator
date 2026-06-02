import subprocess
import time
from src.models.job import Job
from src.orchestrator.executors.base import BaseExecutor, ExecutionResult

class ShellExecutor(BaseExecutor):
    def execute(self, job: Job) -> ExecutionResult:
        command = job.payload.get("command")
        if not command:
            return ExecutionResult(success=False, exit_code=1,error_message="missing payload.command")

        timeout = job.payload.get("timeout") or max(job.estimated_duration * 2, 10)
        start = time.time()

        try:
            result = subprocess.run(command, shell=True, timeout=timeout, capture_output=True, text=True, timeout=timeout)
            return ExecutionResult(
                success=result.returncode == 0,
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                duration_seconds=time.time() - start,
            )
        except subprocess.TimeoutExpired as e:
            return ExecutionResult(
                success=False,
                exit_code=1,
                stderr=str(e),
                duration_seconds = time.time() - start,
                error_message=f"Command timed out after {timeout} seconds",
            )