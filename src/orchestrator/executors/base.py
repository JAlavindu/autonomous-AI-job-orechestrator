from dataclasses import dataclass
from abc import ABC, abstractmethod
from src.models.job import Job

@dataclass
class ExecutionResult:
    success: bool
    exit_code: int=0
    stdout: str = ""
    stderr:str = ""
    duration_seconds: float = 0.0
    error_message: str | None = None

class BaseExecutor(ABC):
    @abstractmethod
    def execute(self, job: Job) -> ExecutionResult:
        """Run the job and return a structured result."""
        ...