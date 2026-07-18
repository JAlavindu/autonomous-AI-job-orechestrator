import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.admin_routes import router as admin_router
from src.api.health import router as health_router
from src.api.routes import router as api_router
from src.auth.service import api_key_service
from src.core.config import settings
from src.core.logging_config import RequestIdMiddleware, get_logger, setup_logging
from src.db.stream_queue import job_stream
from src.storage.log_store import log_store
from src.tenancy.middleware import RequestSizeLimitMiddleware
from src.core.secrets import hydrate_settings_from_secrets

setup_logging(settings.LOG_LEVEL)
logger = get_logger(__name__)

from src.orchestrator.scheduler import scheduler  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    hydrate_settings_from_secrets(settings)
    settings.validate_secrets_for_environment()
    log_store.root.mkdir(parents=True, exist_ok=True)
    job_stream.ensure_group()

    if settings.AUTH_ENABLED:
        api_key_service.bootstrap_if_empty()

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
app.add_middleware(RequestSizeLimitMiddleware)
app.include_router(health_router)
app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(admin_router, prefix=settings.API_V1_STR)


@app.get("/")
def root():
    return {"message": "Autonomous AI Job Orchestrator is running"}