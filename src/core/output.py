from src.core.config import settings


def truncate_output(text: str | None, limit: int | None = None) -> str:
    if text is None:
        return ""
    max_len = limit or settings.MAX_RUN_OUTPUT_CHARS
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"\n...[truncated {len(text) - max_len} chars]"