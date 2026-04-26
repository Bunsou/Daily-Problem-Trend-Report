import json
import os
from datetime import datetime

CACHE_DIR = ".cache"


def cache_path(name: str) -> str:
    """Return cache file path for today."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    return f"{CACHE_DIR}/{name}_{today}.json"


def save_cache(name: str, data) -> None:
    """Save data to today's cache."""
    with open(cache_path(name), "w") as f:
        json.dump(data, f, indent=2)


def load_cache(name: str):
    """Load today's cache if it exists, else None."""
    path = cache_path(name)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


# === Pipeline output caching (separate from date-keyed fetcher cache) ===

PIPELINE_OUTPUT_FILE = f"{CACHE_DIR}/pipeline_output.json"


def save_pipeline_output(problems) -> None:
    """
    Persist the final scored + novelty-enriched output of the pipeline.
    
    Unlike the date-keyed fetcher cache, this is a single rolling file
    that always holds the most recent run's output. Used for fast 
    iteration on the deliverer without re-running expensive AI stages.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(PIPELINE_OUTPUT_FILE, "w") as f:
        json.dump(problems, f, indent=2)
    print(f"Saved pipeline output to {PIPELINE_OUTPUT_FILE} ({len(problems)} problems).")


def load_pipeline_output():
    """
    Load the most recently cached pipeline output.
    
    Returns:
        A list of scored problem dicts, or None if no cache exists.
    """
    if not os.path.exists(PIPELINE_OUTPUT_FILE):
        return None
    
    try:
        with open(PIPELINE_OUTPUT_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Warning: could not read pipeline cache: {e}")
        return None