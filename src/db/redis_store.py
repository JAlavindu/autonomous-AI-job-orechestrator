import redis

from src.core.config import settings
from src.core.logging_config import get_logger

logger = get_logger(__name__)


class RedisClient:
    """Shared Redis connection for streams, leases, and cache."""

    def __init__(self):
        self.client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True,
        )

    def ping(self) -> bool:
        try:
            return bool(self.client.ping())
        except redis.RedisError as exc:
            logger.error("Redis ping failed: %s", exc)
            return False


redis_client = RedisClient()