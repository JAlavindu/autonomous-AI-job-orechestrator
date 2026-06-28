from typing import List, Optional

import redis

from src.core.config import settings
from src.core.logging_config import get_logger
from src.models.job import Job

logger = get_logger(__name__)


class RedisClient:
    def __init__(self):
        self.client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True,
        )

    def save_job(self, job: Job) -> bool:
        try:
            key = f"job:{job.id}"
            pipe = self.client.pipeline()
            pipe.set(key, job.model_dump_json())
            pipe.sadd("jobs:index", job.id)
            pipe.execute()
            return True
        except Exception as e:
            logger.error("Redis error saving job %s: %s", job.id, e)
            return False

    def get_job(self, job_id: str) -> Optional[Job]:
        try:
            key = f"job:{job_id}"
            data = self.client.get(key)
            if data:
                return Job.model_validate_json(data)
            return None
        except Exception as e:
            logger.error("Redis error retrieving job %s: %s", job_id, e)
            return None

    def get_all_jobs(self) -> List[Job]:
        try:
            job_ids = self.client.smembers("jobs:index")
            if not job_ids:
                return []

            keys = [f"job:{jid}" for jid in job_ids]
            json_data_list = self.client.mget(keys)

            jobs = []
            for data in json_data_list:
                if data:
                    jobs.append(Job.model_validate_json(data))
            return jobs
        except Exception as e:
            logger.error("Redis error listing jobs: %s", e)
            return []

    def delete_job(self, job_id: str) -> bool:
        try:
            key = f"job:{job_id}"
            pipe = self.client.pipeline()
            pipe.delete(key)
            pipe.srem("jobs:index", job_id)
            pipe.execute()
            return True
        except Exception as e:
            logger.error("Redis error deleting job %s: %s", job_id, e)
            return False

    def add_to_queue(self, job_id: str):
        self.client.rpush("queue:jobs", job_id)

    def pop_from_queue(self) -> Optional[str]:
        result = self.client.blpop("queue:jobs", timeout=5)
        if result:
            return result[1]
        return None


redis_client = RedisClient()
