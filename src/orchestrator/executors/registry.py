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

def executor_error_if_disallowed(
    job: Job, executor_allowlist: set[str] | None = None
) -> ExecutionResult | None:
    """Return an error ExecutionResult if the job's executor type is not permitted, else None.

    Single-sourced so both the in-process dispatch (execute_job) and the isolated runner can
    reject a disallowed executor without spawning a child process.
    """
    job_type = job.payload.get("type") or "sleep"
    allowlist = executor_allowlist or settings.executor_allowlist
    if job_type not in allowlist:
        return ExecutionResult(
            success=False,
            exit_code=1,
            error_message=f"Executor '{job_type}' is disabled by tenant policy",
        )
    return None


def execute_job(job: Job, executor_allowlist: set[str] | None = None) -> ExecutionResult:
    job_type = job.payload.get("type") or "sleep"

    disallowed = executor_error_if_disallowed(job, executor_allowlist)
    if disallowed is not None:
        return disallowed

    executor = _EXECUTORS.get(job_type)
    if not executor:
        return ExecutionResult(success=False, exit_code=1, error_message=f"Unknown payload.type: {job_type}")

    return executor.execute(job)