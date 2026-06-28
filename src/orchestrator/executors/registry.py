from src.models.job import Job
from src.orchestrator.executors.base import BaseExecutor, ExecutionResult
from src.orchestrator.executors.shell import ShellExecutor
from src.orchestrator.executors.python_module import PythonModuleExecutor
from src.orchestrator.executors.sleep import SleepExecutor
from src.core.config import settings

_EXECUTORS: dict[str, BaseExecutor] = {
    "shell": ShellExecutor(),
    "python": PythonModuleExecutor(),
    "sleep": SleepExecutor(),
}

def execute_job(job: Job) -> ExecutionResult:
    job_type = job.payload.get("type") or "sleep"

    if job_type not in settings.executor_allowlist:
        return ExecutionResult(
            success=False,
            exit_code=1,
            error_message=f"Executor '{job_type}' is disabled by policy (not in EXECUTOR_ALLOWLIST)",
        )
    executor = _EXECUTORS.get(job_type)
    if not executor:
        return ExecutionResult(success=False, exit_code=1, error_message=f"Unknown payload.type: {job_type}")
    
    return executor.execute(job)