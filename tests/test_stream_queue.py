import uuid

import pytest
import redis as redis_lib

from src.core.config import settings
from src.db.stream_queue import JobStreamQueue


def _redis_up() -> bool:
    try:
        client = redis_lib.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        client.ping()
        return True
    except redis_lib.RedisError:
        return False


@pytest.fixture
def stream_queue():
    q = JobStreamQueue()
    q.ensure_group()
    # Use a unique stream per test run to avoid collisions
    test_key = f"{settings.JOB_STREAM_KEY}:test:{uuid.uuid4().hex[:8]}"
    q.stream_key = test_key
    q.ensure_group()
    yield q
    q.client.delete(test_key)


@pytest.mark.skipif(not _redis_up(), reason="Redis required")
def test_enqueue_read_ack_roundtrip(stream_queue):
    job_id = str(uuid.uuid4())
    stream_queue.enqueue(job_id)

    msg = stream_queue.read("test-consumer-1")
    assert msg is not None
    assert msg.job_id == job_id

    acked = stream_queue.ack(msg.message_id)
    assert acked == 1
    assert stream_queue.pending_count() == 0


@pytest.mark.skipif(not _redis_up(), reason="Redis required")
def test_poison_message_without_job_id_is_acked(stream_queue):
    stream_queue.client.xadd(stream_queue.stream_key, {"bad": "payload"})
    msg = stream_queue.read("test-consumer-2")
    assert msg is None