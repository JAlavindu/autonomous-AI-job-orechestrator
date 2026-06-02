import importlib
import time
import traceback
from src.models.job import Job
from src.orchestrator.executors.base import BaseExecutor, ExecutionResult

class PythonModuleExecutor(BaseExecutor):
    def execute(self, job: Job) -> ExecutionResult:
        module_name = job.payload.get("module")
        function_name = job.payload.get("function")
        args = job.payload.get("args", {})

        if not module_name or not function_name:
            return ExecutionResult(success=False, exit_code=1,error_message="missing payload.module or payload.function")
        
        start=time.time()

        try:
            module = importlib.import_module(module_name)
            func = getattr(module, function_name)
            result = func(**args)
            return ExecutionResult(
                success=True,
                exit_code=0,
                stdout=str(result) if result is not None else "",
                duration_seconds=time.time() - start,
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                exit_code=1,
                stderr=traceback.format_exc(),
                duration_seconds=time.time() - start,
                error_message=f"Error executing {module_name}.{function_name}: {str(e)}",
            )