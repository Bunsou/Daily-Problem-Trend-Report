"""
SQLAlchemy plumbing for the novelty history store.

Defines the declarative Base, the NoveltyHistory model, and the engine /
session factories. No business logic lives here — callers in history.py
own all reads and writes.
"""
from datetime import datetime, date
from typing import Optional

from sqlalchemy import Date, DateTime, Integer, Numeric, String, create_engine, func
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from config import DATABASE_URL


class Base(DeclarativeBase):
    """Declarative base for all ORM models in this project."""
    pass


class NoveltyHistory(Base):
    """One row per (run_date, problem_name) snapshot of a scored problem."""
    __tablename__ = "novelty_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    problem_name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    opportunity_score: Mapped[float] = mapped_column(Numeric(4, 1), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


_engine: Optional[Engine] = None


def get_engine() -> Engine:
    """Return a process-wide cached SQLAlchemy engine bound to DATABASE_URL."""
    global _engine
    if _engine is None:
        if not DATABASE_URL:
            raise RuntimeError(
                "DATABASE_URL is not set. Add it to your .env file. "
                "Format: postgresql+psycopg2://user:pass@host/dbname?sslmode=require"
            )
        _engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
    return _engine


def get_session() -> Session:
    """Return a new Session bound to the shared engine. Use as a context manager."""
    return Session(get_engine())
