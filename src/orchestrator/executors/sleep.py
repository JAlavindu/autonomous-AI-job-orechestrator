from dataClass import dataclass

@dataclass
class ExecutionResult:
    success: bool
    exit_code: int=0
    stdout: str = ""
    stderr:str = ""
    duration_seconds: float = 0.0
    error_message: str | None = None