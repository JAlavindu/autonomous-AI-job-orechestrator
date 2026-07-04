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
    LOG_STORAGE_ROOT: str = "data/logs"
    LOG_SPILL_THRESHOLD_CHARS: int = 4096
    LOG_INLINE_PREVIEW_CHARS: int = 2048

    API_URL: str = "http://localhost:8000"

    # --- Phase 2 auth ---
    AUTH_ENABLED: bool = True
    API_KEY_PEPPER: str = "change-me-in-production"
    API_KEY_HEADER: str = "X-API-Key"
    AUTH_BOOTSTRAP_OPERATOR_KEY: str = ""

    MAX_REQUEST_BODY_BYTES: int = 1_048_576
    MAX_JOB_PAYLOAD_BYTES: int = 65_536
    MAX_JOB_DEPENDENCIES: int = 50
    MAX_DAG_JOBS: int = 100
    DEFAULT_TENANT_MAX_JOBS: int = 1000
    DEFAULT_TENANT_RATE_LIMIT: int = 120
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    ENVIRONMENT: str = "development"  # development | staging | production
    SECRETS_BACKEND: str = "env"  # env | vault

    JWT_ENABLED: bool = True
    JWT_SECRET_KEY: str = "dev-only-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_ISSUER: str = "autonomous-ai-job-orchestrator"
    JWT_AUDIENCE: str = "orchestrator-api"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # HashVault KV v2 (optional; only when SECRETS_BACKEND=vault)
    VAULT_ADDR: str = ""
    VAULT_TOKEN: str = ""
    VAULT_MOUNT: str = "secret"
    VAULT_PATH: str = "orchestrator"

    @property
    def executor_allowlist(self) -> set[str]:
        return {e.strip() for e in self.EXECUTOR_ALLOWLIST.split(",") if e.strip()}

    class Config:
        env_file = ".env"


settings = Settings()