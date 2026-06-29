from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import settings


@lru_cache(maxsize=1)
def get_engine():
    return create_engine(settings.DATABASE_URL, pool_pre_ping=True, future=True)


def SessionLocal() -> Session:
    factory = sessionmaker(
        bind=get_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )
    return factory()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
