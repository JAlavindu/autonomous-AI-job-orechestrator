from src.models.job import Job
import src.orchestrator.executors.registry as registry


def test_shell_disabled_by_default(monkeypatch):
    monkeypatch.setattr(registry.settings, "EXECUTOR_ALLOWLIST", "sleep")
    job = Job(name="evil", estimated_duration=1,
              payload={"type": "shell", "command": "echo pwned"})
    result = registry.execute_job(job)
    assert result.success is False
    assert "disabled by policy" in result.error_message


def test_shell_runs_when_allowlisted(monkeypatch):
    monkeypatch.setattr(registry.settings, "EXECUTOR_ALLOWLIST", "sleep,shell")
    job = Job(name="ok", estimated_duration=1,
              payload={"type": "shell", "command": "echo hi"})
    result = registry.execute_job(job)
    assert result.success is True
    assert "hi" in result.stdout