import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.core.config import settings
from src.core.logging_config import RequestIdMiddleware, get_logger, setup_logging
from src.api.routes import router as api_router

setup_logging(settings.LOG_LEVEL)
logger = get_logger(__name__)

# Import scheduler after logging is configured (module creates Scheduler on import).
from src.orchestrator.scheduler import scheduler  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting scheduler")
    scheduler_task = asyncio.create_task(scheduler.run())

    yield

    logger.info("Stopping scheduler")
    scheduler.stop()
    scheduler_task.cancel()


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(RequestIdMiddleware)
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/")
def root():
    return {"message": "Autonomous AI Job Orchestrator is running"}
