from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from src.core.config import settings
from src.core.logging_config import get_logger
from src.models.job import Job
from src.orchestrator.executors.base import ExecutionResult
from src.orchestrator.executors.registry import executor_error_if_disallowed
from src.orchestrator.runners.base import Runner

logger = get_logger(__name__)

# .../src/orchestrator/runners/subprocess_runner.py -> repo root is parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHILD_MODULE = "src.orchestrator.runners.child"


class SubprocessRunner(Runner):
    """Runs each job in a fresh child Python interpreter with resource limits and a hard timeout."""

    def _timeout_seconds(self, job: Job) -> float:
        if job.resource_req and job.resource_req.timeout_seconds:
            return float(job.resource_req.timeout_seconds)
        return float(settings.DEFAULT_JOB_TIMEOUT_SECONDS)

    def _limits(self, job: Job) -> dict:
        cpu = settings.DEFAULT_JOB_CPU_SECONDS
        mem = settings.DEFAULT_JOB_MEMORY_MB
        if job.resource_req:
            if job.resource_req.cpu_seconds:
                cpu = job.resource_req.cpu_seconds
            if job.resource_req.memory_mb:
                mem = job.resource_req.memory_mb
        return {"cpu_seconds": cpu, "memory_mb": mem}

    def run(self, job: Job, executor_allowlist: set[str] | None = None) -> ExecutionResult:
        # Reject disallowed executors without paying for a process spawn.
        disallowed = executor_error_if_disallowed(job, executor_allowlist)
        if disallowed is not None:
            return disallowed

        timeout = self._timeout_seconds(job)
        envelope = {
            "job": job.model_dump(mode="json"),
            "executor_allowlist": sorted(executor_allowlist) if executor_allowlist is not None else None,
            "limits": self._limits(job),
        }

        fd, result_path = tempfile.mkstemp(prefix="run_", suffix=".json")
        os.close(fd)
        envelope["result_path"] = result_path

        popen_kwargs: dict = {}
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True

        start = time.time()
        proc = subprocess.Popen(
            [sys.executable, "-m", _CHILD_MODULE],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(_REPO_ROOT),
            **popen_kwargs,
        )

        try:
            _, stderr = proc.communicate(json.dumps(envelope), timeout=timeout)
        except subprocess.TimeoutExpired:
            self._kill(proc)
            try:
                _, stderr = proc.communicate(timeout=settings.JOB_TIMEOUT_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                stderr = ""
            self._cleanup(result_path)
            logger.warning("Job %s killed after exceeding timeout %.1fs", job.id, timeout)
            return ExecutionResult(
                success=False,
                exit_code=124,
                duration_seconds=time.time() - start,
                error_message=f"Job exceeded wall-clock timeout of {timeout:.0f}s",
            )

        duration = time.time() - start
        result = self._read_result(result_path, exit_code=proc.returncode, stderr=stderr, duration=duration)
        self._cleanup(result_path)
        return result

    def _read_result(
        self, result_path: str, exit_code: int, stderr: str, duration: float
    ) -> ExecutionResult:
        try:
            with open(result_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            # Child died before writing a result (e.g. RLIMIT_CPU SIGXCPU, segfault, hard kill).
            return ExecutionResult(
                success=False,
                exit_code=exit_code if exit_code else 1,
                stderr=(stderr or "")[-4096:],
                duration_seconds=duration,
                error_message=f"Runner child exited without a result (exit_code={exit_code})",
            )
        return ExecutionResult(**data)

    def _kill(self, proc: subprocess.Popen) -> None:
        try:
            if sys.platform == "win32":
                proc.kill()
            else:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass

    def _cleanup(self, result_path: str) -> None:
        try:
            os.unlink(result_path)
        except OSError:
            pass
