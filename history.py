"""
Persistence layer for past problem outputs.

Stores the top scored problems from each day in Postgres so the novelty
detector can compare today's findings against recent history. The storage
backend is a single `novelty_history` table; see `db.py` and the Alembic
migration for the schema.

All public functions degrade gracefully if the database is unreachable —
they log a warning and return safe defaults rather than raising, so a
DB outage cannot crash the pipeline.
"""
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import SQLAlchemyError

from db import NoveltyHistory, get_session

if TYPE_CHECKING:
    from scorer import ScoredProblem


HISTORY_WINDOW_DAYS = 7


def save_todays_problems(problems: list["ScoredProblem"]) -> None:
    """
    Persist today's top scored problems to the database.

    Idempotent: if rows for today already exist, they are deleted and
    replaced in a single transaction so re-running the pipeline on the
    same day doesn't accumulate duplicates.

    On any database error, logs a warning and returns without raising.
    """
    if not problems:
        return

    today = datetime.now().date()

    try:
        with get_session() as session:
            session.execute(
                delete(NoveltyHistory).where(NoveltyHistory.run_date == today)
            )
            session.add_all(
                NoveltyHistory(
                    run_date=today,
                    problem_name=p["problem_name"],
                    description=p["description"],
                    category=p["category"],
                    opportunity_score=p["opportunity_score"],
                )
                for p in problems
            )
            session.commit()
    except SQLAlchemyError as e:
        print(f"Warning: could not save today's history to database: {e}")
    except Exception as e:
        print(f"Warning: unexpected error saving today's history: {e}")


def load_recent_history(days: int = HISTORY_WINDOW_DAYS) -> list[dict]:
    """
    Load problems from the past N days, excluding today.

    Returns a flat list of {problem_name, description, category, date,
    days_ago} dicts, ordered by most recent run_date first. On any
    database error, logs a warning and returns an empty list so the
    pipeline can continue (every problem will be tagged "new").
    """
    today = datetime.now().date()
    start = today - timedelta(days=days)
    end = today - timedelta(days=1)

    try:
        with get_session() as session:
            rows = session.execute(
                select(NoveltyHistory)
                .where(NoveltyHistory.run_date >= start)
                .where(NoveltyHistory.run_date <= end)
                .order_by(NoveltyHistory.run_date.desc())
            ).scalars().all()
    except SQLAlchemyError as e:
        print(f"Warning: could not load recent history from database: {e}")
        return []
    except Exception as e:
        print(f"Warning: unexpected error loading recent history: {e}")
        return []

    return [
        {
            "problem_name": row.problem_name,
            "description": row.description,
            "category": row.category,
            "date": row.run_date.strftime("%Y-%m-%d"),
            "days_ago": (today - row.run_date).days,
        }
        for row in rows
    ]


def cleanup_old_history(keep_days: int = 30) -> int:
    """
    Delete history rows older than keep_days. Optional housekeeping.

    Returns the number of rows deleted. On any database error, logs a
    warning and returns 0.
    """
    today = datetime.now().date()
    cutoff = today - timedelta(days=keep_days)

    try:
        with get_session() as session:
            result: CursorResult = session.execute(  # type: ignore[assignment]
                delete(NoveltyHistory).where(NoveltyHistory.run_date < cutoff)
            )
            session.commit()
            return result.rowcount or 0
    except SQLAlchemyError as e:
        print(f"Warning: could not clean up old history: {e}")
        return 0
    except Exception as e:
        print(f"Warning: unexpected error cleaning up old history: {e}")
        return 0
