"""Isolated child entrypoint for the SubprocessRunner.

Invoked as ``python -m src.orchestrator.runners.child`` with a JSON envelope on stdin:

    {
      "job": {...},                     # Job.model_dump(mode="json")
      "executor_allowlist": ["sleep"],  # or null for the global default
      "limits": {"cpu_seconds": 1.0, "memory_mb": 128},
      "result_path": "/abs/path/result.json"
    }

Applies best-effort OS resource limits (Unix only), runs the job's executor via the shared
``execute_job`` dispatch, and writes the resulting ExecutionResult as JSON to ``result_path``.
The result is written to a file (not stdout) so job code that prints cannot corrupt the protocol.
"""

from __future__ import annotations

import dataclasses
import json
import sys


def _apply_limits(limits: dict) -> None:
    """Best-effort CPU/memory caps via setrlimit. No-op on non-Unix platforms."""
    if sys.platform == "win32":
        return
    try:
        import resource
    except ImportError:  # pragma: no cover - platform-dependent
        return

    memory_mb = limits.get("memory_mb") or 0
    if memory_mb > 0:
        nbytes = int(memory_mb) * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (nbytes, nbytes))
        except (ValueError, OSError):
            pass

    cpu_seconds = limits.get("cpu_seconds") or 0
    if cpu_seconds > 0:
        secs = int(cpu_seconds)
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (secs, secs))
        except (ValueError, OSError):
            pass


def _write_result(result_path: str, result) -> None:
    with open(result_path, "w", encoding="utf-8") as fh:
        json.dump(dataclasses.asdict(result), fh)


def main() -> int:
    envelope = json.loads(sys.stdin.read())
    result_path = envelope["result_path"]

    # Imports happen after reading the envelope so limit-application failures are still reportable.
    from src.models.job import Job
    from src.orchestrator.executors.base import ExecutionResult
    from src.orchestrator.executors.registry import execute_job

    try:
        _apply_limits(envelope.get("limits") or {})
        job = Job(**envelope["job"])
        allowlist_raw = envelope.get("executor_allowlist")
        allowlist = set(allowlist_raw) if allowlist_raw is not None else None
        result = execute_job(job, executor_allowlist=allowlist)
    except MemoryError:
        result = ExecutionResult(
            success=False,
            exit_code=137,
            error_message="Job exceeded its memory limit",
        )
    except Exception as exc:  # noqa: BLE001 - report any failure back to the parent
        import traceback

        result = ExecutionResult(
            success=False,
            exit_code=1,
            stderr=traceback.format_exc(),
            error_message=f"Runner child error: {exc}",
        )

    _write_result(result_path, result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
