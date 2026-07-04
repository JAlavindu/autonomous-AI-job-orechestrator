import redis
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from src.core.config import settings
from src.db.session import SessionLocal

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/ready")
def ready():
    checks: dict[str, str] = {}

    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = str(exc)

    try:
        client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        client.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = str(exc)

    healthy = all(value == "ok" for value in checks.values())
    body = {"status": "ok" if healthy else "degraded", "checks": checks}
    return JSONResponse(status_code=200 if healthy else 503, content=body)