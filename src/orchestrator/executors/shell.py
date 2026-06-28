import subprocess
import time
from src.models.job import Job
from src.orchestrator.executors.base import BaseExecutor, ExecutionResult

MAX_OUTPUT_SIZE = 64 * 1024 # 64KB

def _truncate(text:str, limit: int = MAX_OUTPUT_SIZE) -> str:
    if text is None:
        return ""
    if len(text) > limit:
        return text[:limit] + f"\n...[truncated {len(text) - limit} chars]"
    return text

class ShellExecutor(BaseExecutor):
    def execute(self, job: Job) -> ExecutionResult:
        command = job.payload.get("command")
        if not command:
            return ExecutionResult(success=False, exit_code=1, error_message="missing payload.command")
        timeout = job.payload.get("timeout") or max(job.estimated_duration * 2, 10)
        start = time.time()
        try:
            result = subprocess.run(
                command,
                shell=True,
                timeout=timeout,
                capture_output=True,
                text=True,
            )
            return ExecutionResult(
                success=result.returncode == 0,
                exit_code=result.returncode,
                stdout=_truncate(result.stdout),
                stderr=_truncate(result.stderr),
                duration_seconds=time.time() - start,
            )
        except subprocess.TimeoutExpired as e:
            return ExecutionResult(
                success=False,
                exit_code=1,
                stderr=_truncate(str(e)),
                duration_seconds=time.time() - start,
                error_message=f"Command timed out after {timeout} seconds",
            )