from __future__ import annotations

import redis

from src.core.config import settings
from src.core.logging_config import get_logger

logger = get_logger(__name__)


class JobLeaseStore:
    """Redis-backed worker lease with TTL (heartbeat extends expiry)."""

    def __init__(self, client: redis.Redis | None = None):
        self.client = client or redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True,
        )
        self.prefix = settings.LEASE_KEY_PREFIX
        self.ttl_seconds = settings.LEASE_TTL_SECONDS

    def _key(self, job_id: str) -> str:
        return f"{self.prefix}{job_id}"

    def acquire(self, job_id: str, worker_id: str, ttl_seconds: int | None = None) -> bool:
        ttl = ttl_seconds or self.ttl_seconds
        acquired = self.client.set(self._key(job_id), worker_id, nx=True, ex=ttl)
        if acquired:
            logger.debug("Lease acquired job=%s worker=%s ttl=%ss", job_id, worker_id, ttl)
        return bool(acquired)

    def renew(self, job_id: str, worker_id: str, ttl_seconds: int | None = None) -> bool:
        ttl = ttl_seconds or self.ttl_seconds
        key = self._key(job_id)
        current = self.client.get(key)
        if current != worker_id:
            return False
        self.client.expire(key, ttl)
        return True

    def release(self, job_id: str, worker_id: str) -> None:
        key = self._key(job_id)
        current = self.client.get(key)
        if current == worker_id:
            self.client.delete(key)
            logger.debug("Lease released job=%s worker=%s", job_id, worker_id)

    def get_holder(self, job_id: str) -> str | None:
        return self.client.get(self._key(job_id))


lease_store = JobLeaseStore()