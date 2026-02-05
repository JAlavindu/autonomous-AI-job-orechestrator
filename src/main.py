import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.core.config import settings
from src.api.routes import router as api_router
from src.orchestrator.scheduler import scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handle app startup and shutdown events.
    """
    # [Startup] Start the scheduler loop in the background
    print("[-] Starting Scheduler...")
    scheduler_task = asyncio.create_task(scheduler.run())
    
    yield  # The application runs here
    
    # [Shutdown] Stop the scheduler cleanly
    print("[-] Stopping Scheduler...")
    scheduler.stop()
    # We can also wait for the task to cancel if needed, check asyncio docs for strict cleanup

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan  # Register the lifespan handler
)

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
def root():
return {"message": "Autonomous AI Job Orchestrator is running"}