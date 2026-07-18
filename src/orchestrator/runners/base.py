from abc import ABC, abstractmethod

from src.models.job import Job
from src.orchestrator.executors.base import ExecutionResult


class Runner(ABC):
    """Executes a job in isolation from the worker process and returns a structured result.

    Implementations must never let job code run in, or crash, the calling worker: the job runs in
    a child process (or container) with resource limits and a hard wall-clock timeout applied.
    """

    @abstractmethod
    def run(self, job: Job, executor_allowlist: set[str] | None = None) -> ExecutionResult:
        """Run the job in isolation and return its ExecutionResult."""
        ...
