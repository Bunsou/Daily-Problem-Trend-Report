"""
Stage-level caching with automatic retry for the daily pipeline.

Wraps each pipeline stage so that:
1. Successful outputs are cached to disk for the rest of today
2. Failed stages retry with exponential backoff before giving up
3. Cache misses are transparent — the wrapped function just runs

Cache invalidation is purely date-based: today's caches are valid until
midnight, then ignored. This avoids any complex success-tracking logic.
"""
import json
import os
import time
from datetime import datetime
from typing import Any, Callable, Optional


STAGE_CACHE_DIR = ".cache/stages"

# Retry policy
MAX_RETRY_ATTEMPTS = 5
INITIAL_BACKOFF_SECONDS = 2.0
BACKOFF_MULTIPLIER = 2.0


def _today_str() -> str:
    """Return today's date in YYYY-MM-DD format for cache keys."""
    return datetime.now().strftime("%Y-%m-%d")


def _stage_cache_path(stage_name: str) -> str:
    """Build the path for today's cache of a given stage."""
    return os.path.join(STAGE_CACHE_DIR, f"{stage_name}_{_today_str()}.json")


def _load_stage_cache(stage_name: str) -> Optional[Any]:
    """
    Load today's cached output for a stage, if it exists.
    
    Returns None on cache miss or if the cache file is corrupt.
    """
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
    """Persist a stage's output to today's cache file."""
    os.makedirs(STAGE_CACHE_DIR, exist_ok=True)
    path = _stage_cache_path(stage_name)
    
    try:
        with open(path, "w") as f:
            json.dump(value, f, indent=2)
    except (TypeError, OSError) as e:
        # Cache write failure shouldn't break the pipeline — the run is
        # already successful, just won't be resumable from this point.
        print(f"  ⚠️  Could not write cache for '{stage_name}': {e}")


def _run_with_retry(
    stage_name: str,
    func: Callable,
    args: tuple,
    kwargs: dict,
) -> Any:
    """
    Execute func(*args, **kwargs) with exponential backoff retry.
    
    Retries up to MAX_RETRY_ATTEMPTS times. Re-raises the last exception
    if all attempts fail.
    """
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
    
    # All retries exhausted — re-raise the last error to abort the pipeline.
    # The "if last_error" guard satisfies type checkers; the loop ensures
    # last_error is set whenever we reach this point.
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
    """
    Run a pipeline stage with caching and automatic retry.
    
    Behavior:
    1. If today's cache exists and use_cache=True, return cached value
    2. Otherwise, run func(*args, **kwargs) with up to 5 retries
    3. On success, save the result to today's cache
    4. On total failure, raise the last exception to abort the pipeline
    
    Args:
        stage_name: Identifier for the cache file (e.g., "fetch", "scorer")
        func: The stage function to execute
        *args, **kwargs: Arguments to pass to func
        use_cache: If False, skip cache lookup and force re-execution
    
    Returns:
        The stage's output, either from cache or freshly computed.
    
    Raises:
        Whatever the wrapped function raises if all retries fail.
    """
    if use_cache:
        cached = _load_stage_cache(stage_name)
        if cached is not None:
            print(f"  ⚡ Using cached '{stage_name}' from today")
            return cached
    
    # Cache miss (or bypass) — run the stage with retry
    result = _run_with_retry(stage_name, func, args, kwargs)
    
    # Cache the successful result for any retry later today
    _save_stage_cache(stage_name, result)
    
    return result


def clear_todays_cache() -> int:
    """
    Delete all stage cache files for today.
    
    Useful when a prompt has changed and you want to force fresh execution.
    Used by the --fresh flag in main.py.
    
    Returns:
        Number of cache files deleted.
    """
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
    """
    Delete stage cache files older than keep_days.
    
    Stage caches are only useful within a single day, so anything older
    is just wasting disk. Run occasionally for housekeeping.
    
    Returns:
        Number of cache files deleted.
    """
    if not os.path.exists(STAGE_CACHE_DIR):
        return 0
    
    from datetime import timedelta
    cutoff = datetime.now().date() - timedelta(days=keep_days)
    deleted = 0
    
    for filename in os.listdir(STAGE_CACHE_DIR):
        if not filename.endswith(".json"):
            continue
        
        # Parse the date from the filename (format: stagename_YYYY-MM-DD.json)
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