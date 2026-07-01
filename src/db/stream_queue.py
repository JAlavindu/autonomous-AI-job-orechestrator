from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import redis

from src.core.config import settings
from src.core.logging_config import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class StreamMessage:
    message_id: str
    job_id: str


class JobStreamQueue:
    """Redis Streams work queue with consumer groups and explicit ACK."""

    def __init__(self, client: redis.Redis | None = None):
        self.client = client or redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True,
        )
        self.stream_key = settings.JOB_STREAM_KEY
        self.group = settings.JOB_STREAM_GROUP
        self.block_ms = settings.JOB_STREAM_BLOCK_MS
        self.maxlen = settings.JOB_STREAM_MAXLEN

    def ensure_group(self) -> None:
        try:
            self.client.xgroup_create(
                name=self.stream_key,
                groupname=self.group,
                id="0",
                mkstream=True,
            )
            logger.info("Created stream group %s on %s", self.group, self.stream_key)
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def enqueue(self, job_id: str) -> str:
        message_id = self.client.xadd(
            name=self.stream_key,
            fields={"job_id": job_id},
            maxlen=self.maxlen,
            approximate=True,
        )
        logger.debug("Enqueued job %s as stream message %s", job_id, message_id)
        return message_id

    def read(self, consumer_name: str, count: int = 1) -> Optional[StreamMessage]:
        """Read one new message for this consumer."""
        rows = self.client.xreadgroup(
            groupname=self.group,
            consumername=consumer_name,
            streams={self.stream_key: ">"},
            count=count,
            block=self.block_ms,
        )
        if not rows:
            return None

        _, messages = rows[0]
        if not messages:
            return None

        message_id, fields = messages[0]
        job_id = fields.get("job_id")
        if not job_id:
            logger.warning("Stream message %s missing job_id; acking poison message", message_id)
            self.ack(message_id)
            return None

        return StreamMessage(message_id=message_id, job_id=job_id)

    def ack(self, message_id: str) -> int:
        return self.client.xack(self.stream_key, self.group, message_id)

    def pending_count(self) -> int:
        summary = self.client.xpending(self.stream_key, self.group)
        return int(summary.get("pending", 0) if isinstance(summary, dict) else summary[0])


job_stream = JobStreamQueue()