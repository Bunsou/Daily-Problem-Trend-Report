"""
Persistence layer for past problem outputs.

Stores the top scored problems from each day so the novelty detector
can compare today's findings against recent history.
"""
import json
import os
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scorer import ScoredProblem


HISTORY_DIR = ".cache/history"
HISTORY_WINDOW_DAYS = 7


def _ensure_history_dir() -> None:
    """Create the history directory if it doesn't exist."""
    os.makedirs(HISTORY_DIR, exist_ok=True)


def _history_path(date_str: str) -> str:
    """Build the file path for a given date's history."""
    return os.path.join(HISTORY_DIR, f"{date_str}.json")


def save_todays_problems(problems: list["ScoredProblem"]) -> None:
    """
    Persist today's top scored problems to disk.
    
    Stores only the fields needed for novelty matching, not the full
    ScoredProblem (which includes large fields like solutions).
    """
    _ensure_history_dir()
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Strip down to matching-essential fields. Smaller files, cleaner reads.
    minimal = [
        {
            "problem_name": p["problem_name"],
            "description": p["description"],
            "category": p["category"],
            "opportunity_score": p["opportunity_score"],
        }
        for p in problems
    ]
    
    with open(_history_path(today), "w") as f:
        json.dump(minimal, f, indent=2)


def load_recent_history(days: int = HISTORY_WINDOW_DAYS) -> list[dict]:
    """
    Load problems from the past N days (excluding today).
    
    Returns:
        A flat list of {problem_name, description, category, date, days_ago}
        dicts, sorted with most recent first.
    """
    _ensure_history_dir()
    today = datetime.now().date()
    
    history: list[dict] = []
    
    for days_ago in range(1, days + 1):
        date = today - timedelta(days=days_ago)
        date_str = date.strftime("%Y-%m-%d")
        path = _history_path(date_str)
        
        if not os.path.exists(path):
            continue
        
        try:
            with open(path) as f:
                problems = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: skipping corrupt history file {date_str}: {e}")
            continue
        
        for p in problems:
            history.append({
                **p,
                "date": date_str,
                "days_ago": days_ago,
            })
    
    return history


def cleanup_old_history(keep_days: int = 30) -> None:
    """
    Delete history files older than keep_days. Optional housekeeping.
    
    Run this occasionally to prevent unbounded disk growth.
    """
    _ensure_history_dir()
    today = datetime.now().date()
    cutoff = today - timedelta(days=keep_days)
    
    for filename in os.listdir(HISTORY_DIR):
        if not filename.endswith(".json"):
            continue
        
        try:
            file_date = datetime.strptime(filename[:-5], "%Y-%m-%d").date()
            if file_date < cutoff:
                os.remove(os.path.join(HISTORY_DIR, filename))
        except ValueError:
            # Filename isn't in expected format; skip it
            continue