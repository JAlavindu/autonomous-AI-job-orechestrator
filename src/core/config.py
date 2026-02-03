from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Autonomous AI Job Orchestrator"
    
    # API Config
    API_V1_STR: str = "/api/v1"
    
    # Redis Config
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    
    # RL Config (Placeholders for now)
    RL_MODEL_PATH: str = "rl_engine/checkpoints/model.pth"

    class Config:
        env_file = ".env"

settings = Settings()