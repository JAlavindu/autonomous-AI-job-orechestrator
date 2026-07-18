import sys

import pytest

from src.models.job import Job, ResourceReq
from src.orchestrator.runners.subprocess_runner import SubprocessRunner


def test_sleep_job_runs_in_isolation():
    job = Job(name="s", estimated_duration=0.1, payload={"type": "sleep"})
    result = SubprocessRunner().run(job, executor_allowlist={"sleep"})
    assert result.success is True
    assert "Slept" in result.stdout


def test_timeout_kills_child():
    job = Job(
        name="slow",
        estimated_duration=5,  # SleepExecutor sleeps this long
        payload={"type": "sleep"},
        resource_req=ResourceReq(timeout_seconds=1),
    )
    result = SubprocessRunner().run(job, executor_allowlist={"sleep"})
    assert result.success is False
    assert result.exit_code == 124
    assert "timeout" in result.error_message.lower()


def test_stdout_noise_does_not_corrupt_result():
    job = Job(
        name="noisy",
        estimated_duration=0.1,
        payload={"type": "python", "module": "src.tasks.demo", "function": "noisy_task"},
    )
    result = SubprocessRunner().run(job, executor_allowlist={"python"})
    assert result.success is True
    assert result.stdout == "done"  # the returned value, not the printed noise


def test_disallowed_executor_is_not_spawned():
    job = Job(name="evil", estimated_duration=1, payload={"type": "shell", "command": "echo hi"})
    result = SubprocessRunner().run(job, executor_allowlist={"sleep"})
    assert result.success is False
    assert "disabled by tenant policy" in result.error_message


@pytest.mark.skipif(sys.platform == "win32", reason="setrlimit unavailable on Windows")
def test_memory_limit_kills_job():
    job = Job(
        name="hog",
        estimated_duration=1,
        payload={"type": "python", "module": "src.tasks.demo", "function": "memory_hog"},
        resource_req=ResourceReq(memory_mb=256),
    )
    result = SubprocessRunner().run(job, executor_allowlist={"python"})
    assert result.success is False
