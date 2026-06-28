from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "Autonomous AI Job Orchestrator"

    # API Config
    API_V1_STR: str = "/api/v1"

    # Redis Config
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    # RL Config
    RL_MODEL_PATH: str = "ai_brain.pth"

    # Executor policy (B3): comma-separated payload "type" values allowed to run.
    EXECUTOR_ALLOWLIST: str = "sleep"

    # Scheduler policy (B4): "heuristic" (default) or "ai".
    SCHEDULER_MODE: str = "heuristic"

    # Logging
    LOG_LEVEL: str = "INFO"

    @property
    def executor_allowlist(self) -> set[str]:
        return {e.strip() for e in self.EXECUTOR_ALLOWLIST.split(",") if e.strip()}

    class Config:
        env_file = ".env"


settings = Settings()
