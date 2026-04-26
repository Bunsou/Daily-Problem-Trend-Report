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