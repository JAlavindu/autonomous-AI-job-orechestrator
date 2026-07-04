from __future__ import annotations

import time

import redis

from src.core.config import settings
from src.core.logging_config import get_logger
from src.db.models import TenantRow
from src.db.session import SessionLocal
from src.tenancy.exceptions import RateLimitExceededError
from src.tenancy.policy import tenant_policy

logger = get_logger(__name__)


class RateLimiter:
    def __init__(self, client: redis.Redis | None = None):
        self.client = client or redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True,
        )

    def _bucket_key(self, tenant_id: str) -> str:
        window = int(time.time()) // settings.RATE_LIMIT_WINDOW_SECONDS
        return f"ratelimit:{tenant_id}:{window}"

    def check(self, tenant_id: str) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return

        with SessionLocal() as db:
            tenant = db.get(TenantRow, tenant_id)
            limit = tenant_policy.rate_limit_for(tenant)

        if limit <= 0:
            return

        key = self._bucket_key(tenant_id)
        try:
            count = self.client.incr(key)
            if count == 1:
                self.client.expire(key, settings.RATE_LIMIT_WINDOW_SECONDS)
            if count > limit:
                raise RateLimitExceededError(
                    f"Rate limit exceeded for tenant ({limit} requests per "
                    f"{settings.RATE_LIMIT_WINDOW_SECONDS}s)"
                )
        except RateLimitExceededError:
            raise
        except redis.RedisError as exc:
            logger.warning("Rate limit check skipped (Redis unavailable): %s", exc)


rate_limiter = RateLimiter()