"""Engine and session factory bound to DATABASE_URL."""
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import settings


_engine: Optional[Engine] = None


def get_engine() -> Engine:
    """Return a process-wide cached SQLAlchemy engine bound to DATABASE_URL."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.database_url, pool_pre_ping=True, future=True
        )
    return _engine


def get_session() -> Session:
    """Return a new Session bound to the shared engine. Use as a context manager."""
    return Session(get_engine())


def dispose_engine() -> None:
    """Close all pooled connections. Called from FastAPI lifespan shutdown."""
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None
