import redis
import json
from typing import Optional, List
from src.core.config import settings
from src.models.job import Job

class RedisClient:
    def __init__(self):
        self.client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True  # Ensures we get strings back instead of bytes
        )

    def save_job(self, job: Job) -> bool:
        """
        Saves a Job object to Redis as a JSON string.
        Also adds the job ID to a set for easy retrieval of 'all jobs'.
        """
        try:
            key = f"job:{job.id}"
            
            # Use a pipeline to ensure atomicity (both operations happen or neither)
            pipe = self.client.pipeline()
            pipe.set(key, job.model_dump_json())
            pipe.sadd("jobs:index", job.id)
            pipe.execute()
            
            return True
        except Exception as e:
            # In production, recommend using the logger defined in utils
            print(f"Redis Error saving job: {e}")
            return False
        
    def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieves a Job object by ID."""
        try:
            key = f"job:{job_id}"
            data = self.client.get(key)
            if data:
                return Job.model_validate_json(data)
            return None
        except Exception as e:
            print(f"Redis Error retrieving job: {e}")
            return None

    def get_all_jobs(self) -> List[Job]:
        """Retrieves all jobs currently tracked in the system."""
        try:
            # Get all IDs from the index set
            job_ids = self.client.smembers("jobs:index")
            if not job_ids:
                return []
            
            # Construct the specific keys for these IDs
            keys = [f"job:{jid}" for jid in job_ids]
            
            # Use mget (multi-get) to fetch all data in one request for performance
            json_data_list = self.client.mget(keys)
            
            jobs = []
            for data in json_data_list:
                if data:
                    jobs.append(Job.model_validate_json(data))
            return jobs
        except Exception as e:
            print(f"Redis Error listing jobs: {e}")
            return []

    def delete_job(self, job_id: str) -> bool:
        """Deletes a job and removes it from the index."""
        try:
            key = f"job:{job_id}"
            pipe = self.client.pipeline()
            pipe.delete(key)
            pipe.srem("jobs:index", job_id)
            pipe.execute()
            return True
        except Exception as e:
            print(f"Redis Error deleting job: {e}")
            return False
            
redis_client = RedisClient()