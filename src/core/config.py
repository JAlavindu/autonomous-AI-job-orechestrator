from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Autonomous AI Job Orchestrator"
    API_V1_STR: str = "/api/v1"

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    RL_MODEL_PATH: str = "ai_brain.pth"
    EXECUTOR_ALLOWLIST: str = "sleep"
    SCHEDULER_MODE: str = "heuristic"
    LOG_LEVEL: str = "INFO"

    DATABASE_URL: str = "postgresql+psycopg2://orchestrator:orchestrator@localhost:5432/orchestrator"
    DEFAULT_TENANT_ID: str = "00000000-0000-0000-0000-000000000001"
    DEFAULT_TENANT_NAME: str = "default"

    JOB_STREAM_KEY: str = "stream:jobs"
    JOB_STREAM_GROUP: str = "workers"
    JOB_STREAM_BLOCK_MS: int = 5000
    JOB_STREAM_MAXLEN: int = 10000
    JOB_STREAM_CLAIM_MIN_IDLE_MS: int = 60000
    RECLAIM_EVERY_N_LOOPS: int = 5

    JOB_DLQ_STREAM_KEY: str = "stream:jobs:dlq"
    JOB_DLQ_MAXLEN: int = 10000

    LEASE_KEY_PREFIX: str = "lease:job:"
    LEASE_TTL_SECONDS: int = 30
    LEASE_HEARTBEAT_SECONDS: int = 10

    MAX_JOB_RETRIES: int = 3
    RETRY_BACKOFF_BASE_SECONDS: float = 2.0
    RETRY_BACKOFF_MAX_SECONDS: float = 300.0

    MAX_RUN_OUTPUT_CHARS: int = 65536

    @property
    def executor_allowlist(self) -> set[str]:
        return {e.strip() for e in self.EXECUTOR_ALLOWLIST.split(",") if e.strip()}

    class Config:
        env_file = ".env"


settings = Settings()