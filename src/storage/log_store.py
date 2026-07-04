from __future__ import annotations

from pathlib import Path

from src.core.config import settings
from src.core.logging_config import get_logger

logger = get_logger(__name__)


class LocalLogStore:
    """Filesystem-backed log storage for dev/single-node deployments."""

    def __init__(self, root: str | None = None):
        self.root = Path(root or settings.LOG_STORAGE_ROOT)
        self.root.mkdir(parents=True, exist_ok=True)

    def write_text(self, relative_path: str, content: str) -> str:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        ref = f"local://{relative_path.replace(chr(92), '/')}"
        logger.debug("Stored log artifact %s (%s bytes)", ref, len(content))
        return ref

    def read_text(self, ref: str) -> str:
        if not ref.startswith("local://"):
            raise ValueError(f"Unsupported log ref scheme: {ref}")
        relative = ref.removeprefix("local://")
        path = self.root / relative
        if not path.exists():
            raise FileNotFoundError(f"Log artifact not found: {ref}")
        return path.read_text(encoding="utf-8")


log_store = LocalLogStore()