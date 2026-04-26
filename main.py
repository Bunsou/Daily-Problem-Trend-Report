"""
Trend-to-problem discovery engine — production runner.

Orchestrates the full pipeline:
  fetch → category filter → AI classifier → analyzer → scorer → novelty → deliver

Each network-touching stage is wrapped with caching and automatic retry.
On retry within the same day, completed stages are reused from cache.

Usage:
    python main.py              # run end-to-end, send to Telegram
    python main.py --no-send    # run end-to-end, print only (no Telegram)
    python main.py --fresh      # ignore today's cache, re-run all stages
"""
import sys
import traceback
from datetime import datetime

from fetcher import fetch_trends
from category_filter import filter_by_category
from classifier import classify_trends
from analyzer import analyze_trends
from scorer import score_problems
from novelty import enrich_with_novelty
from history import save_todays_problems
from cache import save_pipeline_output
from deliverer import deliver
from telegram_client import send_message, TelegramError
from pipeline_cache import cached_stage, clear_todays_cache


def log(message: str) -> None:
    """Print a timestamped log line."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {message}")


def run_pipeline(send_telegram: bool = True, fresh: bool = False) -> int:
    """
    Execute the full pipeline end-to-end with stage-level caching.
    
    Args:
        send_telegram: If True, deliver final briefing via Telegram.
        fresh: If True, clear today's cache before running.
    
    Returns:
        Exit code: 0 on success, 1 on failure.
    """
    log("=" * 60)
    log("Trend Engine — pipeline start")
    log("=" * 60)
    
    if fresh:
        deleted = clear_todays_cache()
        log(f"--fresh: cleared {deleted} cache file(s) from today")
    
    try:
        # Stage 0: Fetch trends (cached, retried)
        log("Stage 0: Fetching trends...")
        trends = cached_stage("fetch", fetch_trends)
        log(f"  Raw trends: {len(trends)}")
        
        if not trends:
            log("⚠️  No trends fetched. Likely a SerpApi issue.")
            _emergency_notify(
                "Trend Engine: no trends fetched today. Check SerpApi quota.",
                send_telegram,
            )
            return 1
        
        # Stage 1a: Category filter (deterministic, no retry/cache needed,
        # but caching is cheap and aids resume from a later stage failure)
        log("Stage 1a: Filtering noise categories...")
        trends = cached_stage("category_filter", filter_by_category, trends)
        log(f"  After category filter: {len(trends)}")
        
        # Stage 1b: AI classifier (cached, retried)
        log("Stage 1b: Running AI classifier...")
        trends = cached_stage("classifier", classify_trends, trends)
        log(f"  After classifier: {len(trends)}")
        
        # Stage 2: Deep analysis (cached, retried)
        log(f"Stage 2: Analyzing {len(trends)} candidates...")
        problems = cached_stage("analyzer", analyze_trends, trends)
        log(f"  Identified problems: {len(problems)}")
        
        # Stage 3: Score as business opportunities (cached, retried)
        log(f"Stage 3: Scoring {len(problems)} problems...")
        scored = cached_stage("scorer", score_problems, problems)
        log(f"  Qualifying opportunities: {len(scored)}")
        
        # Stage 4: Enrich with novelty (cached, retried)
        log("Stage 4: Checking novelty against past 7 days...")
        scored = cached_stage("novelty", enrich_with_novelty, scored)
        
        # Persist final results (these are not stage-cached because
        # they're cross-day artifacts, not within-day resume points)
        save_pipeline_output(scored)
        save_todays_problems(scored)
        log("  Saved pipeline output and today's history.")
        
        # Stage 5: Deliver (retried via cached_stage even though no
        # output to cache — the wrapper still handles retry on Telegram errors)
        log(f"Stage 5: Delivering briefing (telegram={send_telegram})...")
        cached_stage(
            "deliver",
            deliver,
            scored,
            send_telegram=send_telegram,
        )
        
        log("=" * 60)
        log("✅ Pipeline complete")
        log("=" * 60)
        return 0
    
    except TelegramError as e:
        log("=" * 60)
        log(f"⚠️  Telegram delivery failed after retries: {e}")
        log("Briefing was generated — content is in pipeline cache.")
        log("Run `python deliverer.py --send` to retry delivery without re-running pipeline.")
        log("=" * 60)
        return 1
    
    except Exception as e:
        log("=" * 60)
        log(f"❌ Pipeline crashed: {type(e).__name__}: {e}")
        log("Full traceback:")
        traceback.print_exc()
        log("=" * 60)
        
        _emergency_notify(
            f"Trend Engine crashed: {type(e).__name__}: {e}",
            send_telegram,
        )
        return 1


def _emergency_notify(message: str, send_telegram: bool) -> None:
    """Best-effort Telegram notification when the pipeline fails."""
    if not send_telegram:
        return
    
    try:
        send_message(f"🚨 {message}")
    except Exception as notify_error:
        log(f"  (Could not send emergency notification: {notify_error})")


if __name__ == "__main__":
    no_send = "--no-send" in sys.argv
    fresh = "--fresh" in sys.argv
    exit_code = run_pipeline(send_telegram=not no_send, fresh=fresh)
    sys.exit(exit_code)