from src.core.config import settings
from src.orchestrator.runners.base import Runner
from src.orchestrator.runners.subprocess_runner import SubprocessRunner


def get_runner() -> Runner:
    """Select the isolated runner implementation by configuration."""
    if settings.RUNNER == "subprocess":
        return SubprocessRunner()
    # "docker" is the anticipated next implementation (prod isolation); not yet built.
    raise ValueError(f"Unknown RUNNER: {settings.RUNNER!r}")


runner: Runner = get_runner()

__all__ = ["Runner", "SubprocessRunner", "get_runner", "runner"]
