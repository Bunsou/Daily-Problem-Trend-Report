"""
Caching for the daily pipeline.

Two concerns live here:

1. **Stage-level cache + retry** — wraps each pipeline stage so successful
   outputs are reused within the same day and failures retry with backoff.
2. **Pipeline output cache** — a rolling single-file snapshot of the most
   recent pipeline result, used by the deliverer for fast iteration.

Both write to `.cache/` at the project root.
"""
import json
import os
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Optional


CACHE_DIR = ".cache"
STAGE_CACHE_DIR = os.path.join(CACHE_DIR, "stages")
PIPELINE_OUTPUT_FILE = os.path.join(CACHE_DIR, "pipeline_output.json")

MAX_RETRY_ATTEMPTS = 5
INITIAL_BACKOFF_SECONDS = 2.0
BACKOFF_MULTIPLIER = 2.0


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# === Date-keyed fetcher cache (used by fetcher.py for raw_trends) ===

def cache_path(name: str) -> str:
    """Return cache file path for today."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    return f"{CACHE_DIR}/{name}_{_today_str()}.json"


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


# === Rolling pipeline output (used by deliverer.py for dev iteration) ===

def save_pipeline_output(problems) -> None:
    """Persist the final scored + novelty-enriched output of the pipeline."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(PIPELINE_OUTPUT_FILE, "w") as f:
        json.dump(problems, f, indent=2)
    print(f"Saved pipeline output to {PIPELINE_OUTPUT_FILE} ({len(problems)} problems).")


def load_pipeline_output():
    """Load the most recently cached pipeline output, or None."""
    if not os.path.exists(PIPELINE_OUTPUT_FILE):
        return None

    try:
        with open(PIPELINE_OUTPUT_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Warning: could not read pipeline cache: {e}")
        return None


# === Stage-level cache with retry (used by orchestrator.py) ===

def _stage_cache_path(stage_name: str) -> str:
    return os.path.join(STAGE_CACHE_DIR, f"{stage_name}_{_today_str()}.json")


def _load_stage_cache(stage_name: str) -> Optional[Any]:
    path = _stage_cache_path(stage_name)
    if not os.path.exists(path):
        return None

    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  ⚠️  Cache file for '{stage_name}' is corrupt; ignoring: {e}")
        return None


def _save_stage_cache(stage_name: str, value: Any) -> None:
    os.makedirs(STAGE_CACHE_DIR, exist_ok=True)
    path = _stage_cache_path(stage_name)

    try:
        with open(path, "w") as f:
            json.dump(value, f, indent=2)
    except (TypeError, OSError) as e:
        print(f"  ⚠️  Could not write cache for '{stage_name}': {e}")


def _run_with_retry(
    stage_name: str,
    func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Execute func with exponential backoff retry."""
    last_error: Optional[Exception] = None
    backoff = INITIAL_BACKOFF_SECONDS

    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_error = e

            if attempt < MAX_RETRY_ATTEMPTS:
                print(
                    f"  ⚠️  Stage '{stage_name}' attempt {attempt}/{MAX_RETRY_ATTEMPTS} "
                    f"failed: {type(e).__name__}: {e}"
                )
                print(f"  ⏳ Retrying in {backoff:.0f}s...")
                time.sleep(backoff)
                backoff *= BACKOFF_MULTIPLIER
            else:
                print(
                    f"  ❌ Stage '{stage_name}' failed after "
                    f"{MAX_RETRY_ATTEMPTS} attempts."
                )

    if last_error:
        raise last_error
    raise RuntimeError(f"Stage '{stage_name}' failed without an exception")


def cached_stage(
    stage_name: str,
    func: Callable,
    *args,
    use_cache: bool = True,
    **kwargs,
) -> Any:
    """Run a pipeline stage with caching and automatic retry."""
    if use_cache:
        cached = _load_stage_cache(stage_name)
        if cached is not None:
            print(f"  ⚡ Using cached '{stage_name}' from today")
            return cached

    result = _run_with_retry(stage_name, func, args, kwargs)
    _save_stage_cache(stage_name, result)
    return result


def clear_todays_cache() -> int:
    """Delete all stage cache files for today. Returns count deleted."""
    if not os.path.exists(STAGE_CACHE_DIR):
        return 0

    today = _today_str()
    deleted = 0

    for filename in os.listdir(STAGE_CACHE_DIR):
        if filename.endswith(f"_{today}.json"):
            try:
                os.remove(os.path.join(STAGE_CACHE_DIR, filename))
                deleted += 1
            except OSError as e:
                print(f"  ⚠️  Could not delete {filename}: {e}")

    return deleted


def cleanup_old_caches(keep_days: int = 3) -> int:
    """Delete stage cache files older than keep_days. Returns count deleted."""
    if not os.path.exists(STAGE_CACHE_DIR):
        return 0

    cutoff = datetime.now().date() - timedelta(days=keep_days)
    deleted = 0

    for filename in os.listdir(STAGE_CACHE_DIR):
        if not filename.endswith(".json"):
            continue

        try:
            date_part = filename.rsplit("_", 1)[1].replace(".json", "")
            file_date = datetime.strptime(date_part, "%Y-%m-%d").date()
        except (IndexError, ValueError):
            continue

        if file_date < cutoff:
            try:
                os.remove(os.path.join(STAGE_CACHE_DIR, filename))
                deleted += 1
            except OSError:
                pass

    return deleted
