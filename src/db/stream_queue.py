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
    """Redis Streams work queue with consumer groups, ACK, reclaim, and DLQ."""

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
        self.dlq_key = settings.JOB_DLQ_STREAM_KEY
        self.dlq_maxlen = settings.JOB_DLQ_MAXLEN

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

    def _parse_message(self, message_id: str, fields: dict) -> Optional[StreamMessage]:
        job_id = fields.get("job_id")
        if not job_id:
            logger.warning("Stream message %s missing job_id; acking poison message", message_id)
            self.ack(message_id)
            return None
        return StreamMessage(message_id=message_id, job_id=job_id)

    def read(self, consumer_name: str, count: int = 1) -> Optional[StreamMessage]:
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
        return self._parse_message(message_id, fields)

    def claim_stale_messages(
        self,
        consumer_name: str,
        min_idle_ms: int | None = None,
        count: int = 10,
    ) -> list[StreamMessage]:
        """Reclaim pending messages idle longer than min_idle_ms (XAUTOCLAIM)."""
        idle = min_idle_ms or settings.JOB_STREAM_CLAIM_MIN_IDLE_MS
        try:
            result = self.client.xautoclaim(
                self.stream_key,
                self.group,
                consumer_name,
                idle,
                "0-0",
                count=count,
            )
        except redis.ResponseError as exc:
            logger.warning("XAUTOCLAIM failed: %s", exc)
            return []

        # redis-py returns (next_id, messages[, deleted_ids])
        if not result or len(result) < 2:
            return []

        claimed: list[StreamMessage] = []
        for message_id, fields in result[1]:
            parsed = self._parse_message(message_id, fields)
            if parsed:
                claimed.append(parsed)
                logger.info(
                    "Reclaimed stale message %s for job %s -> consumer %s",
                    message_id,
                    parsed.job_id,
                    consumer_name,
                )
        return claimed

    def ack(self, message_id: str) -> int:
        return self.client.xack(self.stream_key, self.group, message_id)

    def send_to_dlq(
        self,
        job_id: str,
        reason: str,
        source_message_id: str | None = None,
    ) -> str:
        message_id = self.client.xadd(
            name=self.dlq_key,
            fields={
                "job_id": job_id,
                "reason": reason or "unknown",
                "source_message_id": source_message_id or "",
            },
            maxlen=self.dlq_maxlen,
            approximate=True,
        )
        logger.warning("Job %s sent to DLQ (%s): %s", job_id, message_id, reason)
        return message_id

    def pending_count(self) -> int:
        summary = self.client.xpending(self.stream_key, self.group)
        return int(summary.get("pending", 0) if isinstance(summary, dict) else summary[0])

    def list_dlq(self, count: int = 100) -> list[dict]:
        rows = self.client.xrevrange(self.dlq_key, max="+", min="-", count=count)
        items: list[dict] = []
        for message_id, fields in rows:
            items.append(
                {
                    "message_id": message_id,
                    "job_id": fields.get("job_id"),
                    "reason": fields.get("reason"),
                    "source_message_id": fields.get("source_message_id"),
                }
            )
        return items


job_stream = JobStreamQueue()