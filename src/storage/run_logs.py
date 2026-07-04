from __future__ import annotations

import json
from dataclasses import dataclass

from src.core.config import settings
from src.core.output import truncate_output
from src.storage.log_store import log_store


@dataclass(frozen=True)
class PersistedRunOutput:
    stdout: str | None
    stderr: str | None
    error: str | None
    log_ref: str | None


def persist_run_output(
    run_id: str,
    stdout: str | None,
    stderr: str | None,
    error: str | None,
) -> PersistedRunOutput:
    refs: dict[str, str] = {}

    stdout_text = stdout or ""
    stderr_text = stderr or ""
    error_text = error or ""

    if len(stdout_text) > settings.LOG_SPILL_THRESHOLD_CHARS:
        refs["stdout"] = log_store.write_text(f"runs/{run_id}/stdout.txt", stdout_text)
        stdout_text = truncate_output(stdout_text, settings.LOG_INLINE_PREVIEW_CHARS)

    if len(stderr_text) > settings.LOG_SPILL_THRESHOLD_CHARS:
        refs["stderr"] = log_store.write_text(f"runs/{run_id}/stderr.txt", stderr_text)
        stderr_text = truncate_output(stderr_text, settings.LOG_INLINE_PREVIEW_CHARS)

    if len(error_text) > settings.LOG_SPILL_THRESHOLD_CHARS:
        refs["error"] = log_store.write_text(f"runs/{run_id}/error.txt", error_text)
        error_text = truncate_output(error_text, settings.LOG_INLINE_PREVIEW_CHARS)

    return PersistedRunOutput(
        stdout=truncate_output(stdout_text) if stdout_text else None,
        stderr=truncate_output(stderr_text) if stderr_text else None,
        error=truncate_output(error_text) if error_text else None,
        log_ref=json.dumps(refs) if refs else None,
    )


def load_full_run_logs(log_ref: str | None, stdout: str | None, stderr: str | None, error: str | None) -> dict:
    """Merge inline DB preview with spilled artifacts when refs exist."""
    result = {
        "stdout": stdout,
        "stderr": stderr,
        "error": error,
        "stdout_ref": None,
        "stderr_ref": None,
        "error_ref": None,
        "spilled": False,
    }
    if not log_ref:
        return result

    try:
        refs = json.loads(log_ref)
    except json.JSONDecodeError:
        return result

    result["stdout_ref"] = refs.get("stdout")
    result["stderr_ref"] = refs.get("stderr")
    result["error_ref"] = refs.get("error")
    result["spilled"] = bool(refs)

    if refs.get("stdout"):
        result["stdout"] = log_store.read_text(refs["stdout"])
    if refs.get("stderr"):
        result["stderr"] = log_store.read_text(refs["stderr"])
    if refs.get("error"):
        result["error"] = log_store.read_text(refs["error"])

    return result