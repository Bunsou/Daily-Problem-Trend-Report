"""
Trend-to-problem discovery engine — production runner.

Orchestrates two independent source chains (Trends and Reddit), merges
their results with semantic deduplication, applies per-source output caps,
and delivers the final briefing.

Each network-touching stage is wrapped with caching and automatic retry.
On retry within the same day, completed stages are reused from cache.
Cache keys are source-scoped (e.g., "fetch_trends", "fetch_reddit") so the
two chains never clobber each other's cached data.

If one source chain fails entirely (bad credentials, network outage), the
pipeline continues with the other source's results rather than aborting.

Usage:
    python -m app.pipeline.orchestrator              # run end-to-end, send to Telegram
    python -m app.pipeline.orchestrator --no-send    # run end-to-end, print only
    python -m app.pipeline.orchestrator --fresh      # ignore today's cache, re-run all stages
"""
import sys
import traceback
from datetime import datetime

from app.pipeline.fetcher import fetch_trends
from app.pipeline.reddit_fetcher import fetch_reddit_posts
from app.pipeline.category_filter import filter_by_category
from app.pipeline.classifier import classify_trends
from app.pipeline.analyzer import analyze_trends
from app.pipeline.scorer import score_problems, ScoredProblem
from app.pipeline.novelty import enrich_with_novelty
from app.pipeline.merger import merge_and_dedupe
from app.pipeline.deliverer import deliver
from app.services.history import save_todays_problems
from app.services.cache import (
    save_pipeline_output,
    cached_stage,
    cleanup_old_caches,
    clear_todays_cache,
)
from app.clients.telegram import send_message, TelegramError


def log(message: str) -> None:
    """Print a timestamped log line."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {message}")


def apply_caps(
    merged: list[ScoredProblem],
    max_trends: int = 4,
    max_reddit: int = 6,
) -> list[ScoredProblem]:
    """
    Cap the merged list by source budget.

    Iterates in score order (highest first). A dual-source entry counts toward
    both budgets and is only kept if both budgets have remaining headroom.

    Args:
        merged: Combined list sorted by opportunity_score descending.
        max_trends: Maximum entries whose sources include "trends".
        max_reddit: Maximum entries whose sources include "reddit".

    Returns:
        Capped list, preserving the input's score ordering.
    """
    trends_count = 0
    reddit_count = 0
    kept: list[ScoredProblem] = []

    for entry in merged:
        sources = entry.get("sources", [])
        has_trends = "trends" in sources
        has_reddit = "reddit" in sources

        if has_trends and trends_count >= max_trends:
            continue
        if has_reddit and reddit_count >= max_reddit:
            continue

        kept.append(entry)
        if has_trends:
            trends_count += 1
        if has_reddit:
            reddit_count += 1

    return kept


def _run_chain(source: str) -> list[ScoredProblem]:
    """
    Run the full pipeline chain for a single source.

    Trends chain:  fetch → category_filter → classifier → analyzer → scorer → novelty
    Reddit chain:  fetch → classifier → analyzer → scorer → novelty
                   (no category_filter — subreddit selection is the filter)

    Every stage uses a source-scoped cache key to prevent cross-chain collisions.

    Returns:
        Scored, novelty-enriched list. May be empty if the source produces no
        qualifying problems. Never raises — callers handle per-source failures.
    """
    if source == "trends":
        log("=== Trends chain ===")

        log("Stage 0: Fetching trends...")
        entries = cached_stage("fetch_trends", fetch_trends)
        log(f"  Raw entries: {len(entries)}")

        if not entries:
            log("⚠️  No trends fetched. Check SerpApi quota.")
            return []

        log("Stage 1a: Filtering noise categories...")
        entries = cached_stage("category_filter_trends", filter_by_category, entries)
        log(f"  After category filter: {len(entries)}")

        log("Stage 1b: AI classifier...")
        entries = cached_stage("classifier_trends", classify_trends, entries)
        log(f"  After classifier: {len(entries)}")

        if not entries:
            log("⚠️  No Trends entries survived the classifier.")
            return []

        log(f"Stage 2: Analyzing {len(entries)} Trends candidates...")
        problems = cached_stage(
            "analyzer_trends", analyze_trends, entries, source="trends"
        )
        log(f"  Identified problems: {len(problems)}")

    else:  # reddit
        log("=== Reddit chain ===")

        log("Stage 0: Fetching Reddit posts...")
        entries = cached_stage("fetch_reddit", fetch_reddit_posts)
        log(f"  Raw entries: {len(entries)}")

        if not entries:
            log("⚠️  No Reddit posts fetched. Check REDDIT_* credentials.")
            return []

        log("Stage 1: AI classifier...")
        entries = cached_stage("classifier_reddit", classify_trends, entries)
        log(f"  After classifier: {len(entries)}")

        if not entries:
            log("⚠️  No Reddit entries survived the classifier.")
            return []

        log(f"Stage 2: Analyzing {len(entries)} Reddit candidates...")
        problems = cached_stage(
            "analyzer_reddit", analyze_trends, entries, source="reddit"
        )
        log(f"  Identified problems: {len(problems)}")

    if not problems:
        log(f"⚠️  No problems extracted from {source}.")
        return []

    log(f"Stage 3: Scoring {len(problems)} problems...")
    scored = cached_stage(f"scorer_{source}", score_problems, problems)
    log(f"  Qualifying opportunities (score ≥ 4.5): {len(scored)}")

    log("Stage 4: Checking novelty against past 7 days...")
    scored = cached_stage(f"novelty_{source}", enrich_with_novelty, scored)

    return scored


def run_pipeline(send_telegram: bool = True, fresh: bool = False) -> int:
    """
    Execute both source chains, merge, cap, and deliver the briefing.

    Args:
        send_telegram: If True, deliver the final briefing via Telegram.
        fresh: If True, clear today's cache before running.

    Returns:
        Exit code: 0 on success, 1 on failure.
    """
    log("=" * 60)
    log("Trend Engine v2 — pipeline start")
    log("=" * 60)

    deleted = cleanup_old_caches(keep_days=3)
    if deleted > 0:
        log(f"Cleaned up {deleted} old cache file(s)")

    if fresh:
        deleted = clear_todays_cache()
        log(f"--fresh: cleared {deleted} cache file(s) from today")

    # ── Source chains — each isolated from the other's failures ────────────
    try:
        trends_scored = _run_chain("trends")
    except Exception as e:
        log(f"⚠️  Trends chain failed: {type(e).__name__}: {e}")
        traceback.print_exc()
        trends_scored = []

    try:
        reddit_scored = _run_chain("reddit")
    except Exception as e:
        log(f"⚠️  Reddit chain failed: {type(e).__name__}: {e}")
        traceback.print_exc()
        reddit_scored = []

    if not trends_scored and not reddit_scored:
        log("❌ Both sources produced zero qualifying results.")
        _emergency_notify(
            "Trend Engine: both sources produced zero results today. "
            "Check SerpApi quota and Reddit credentials.",
            send_telegram,
        )
        return 1

    # ── Merge, dedupe, cap ─────────────────────────────────────────────────
    log("=" * 60)
    log("Merging and deduplicating across sources...")
    merged = merge_and_dedupe(trends_scored, reddit_scored)

    n_trends_tagged = sum(1 for p in merged if "trends" in p.get("sources", []))
    n_reddit_tagged = sum(1 for p in merged if "reddit" in p.get("sources", []))
    log(
        f"  {len(merged)} unique problem(s) "
        f"({n_trends_tagged} from Trends, {n_reddit_tagged} from Reddit)"
    )

    capped = apply_caps(merged, max_trends=4, max_reddit=6)
    n_capped_trends = sum(1 for p in capped if "trends" in p.get("sources", []))
    n_capped_reddit = sum(1 for p in capped if "reddit" in p.get("sources", []))
    log(
        f"  After caps (max 4 Trends, max 6 Reddit): {len(capped)} problem(s) "
        f"({n_capped_trends} Trends, {n_capped_reddit} Reddit)"
    )

    # ── Persist ────────────────────────────────────────────────────────────
    save_pipeline_output(capped)
    save_todays_problems(capped)
    log("  Saved pipeline output and today's history.")

    # ── Deliver ────────────────────────────────────────────────────────────
    log(f"Stage 5: Delivering briefing (telegram={send_telegram})...")
    try:
        cached_stage("deliver", deliver, capped, send_telegram=send_telegram)
    except TelegramError as e:
        log("=" * 60)
        log(f"⚠️  Telegram delivery failed after retries: {e}")
        log("Briefing was generated — content is in pipeline cache.")
        log("Run `python -m app.pipeline.deliverer --send` to retry delivery.")
        log("=" * 60)
        return 1
    except Exception as e:
        log(f"❌ Delivery failed unexpectedly: {type(e).__name__}: {e}")
        traceback.print_exc()
        return 1

    log("=" * 60)
    log("✅ Pipeline complete")
    log("=" * 60)
    return 0


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
