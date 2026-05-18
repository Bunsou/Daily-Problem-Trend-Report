# Task 06 — Restructure the orchestrator for parallel source chains

**Status:** Done
**Depends on:** task02 (reddit fetcher), task03 (analyzer source param), task04 (scorer field), task05 (merger)
**Unblocks:** task07 (deliverer reads new shape), task09 (verification)

## Goal

Replace the single linear flow in `app/pipeline/orchestrator.py` with two source-specific chains that run sequentially, each filtered to `opportunity_score >= 4.5`, then merged, deduped, capped, and delivered. Cache keys must be source-scoped so the two chains never clobber each other.

## Files to touch

- `app/pipeline/orchestrator.py` — rewrite the body of `run_pipeline`.
- Possibly `app/pipeline/__init__.py` — if you want to re-export `run_chain` or `apply_caps`. Optional.

## Implementation steps

### 1. Two source-specific chains

Factor out a helper:

```python
def _run_chain(source: str) -> list[ScoredProblem]:
    """Runs fetch → (filter) → classifier → analyzer → scorer → novelty for one source."""
```

- **`source == "trends"`** chain:
  1. `cached_stage("fetch_trends", fetch_trends)`
  2. `cached_stage("category_filter_trends", filter_by_category, entries)`
  3. `cached_stage("classifier_trends", classify_trends, entries)`
  4. `cached_stage("analyzer_trends", analyze_trends, entries, source="trends")`
  5. `cached_stage("scorer_trends", score_problems, problems)`
  6. `cached_stage("novelty_trends", enrich_with_novelty, scored)`
- **`source == "reddit"`** chain:
  1. `cached_stage("fetch_reddit", fetch_reddit_posts)`
  2. *(skip category_filter — subreddit selection IS the category filter)*
  3. `cached_stage("classifier_reddit", classify_trends, entries)` *(re-uses the same classifier; the classifier is source-agnostic)*
  4. `cached_stage("analyzer_reddit", analyze_trends, entries, source="reddit")`
  5. `cached_stage("scorer_reddit", score_problems, problems)`
  6. `cached_stage("novelty_reddit", enrich_with_novelty, scored)`

**Critical:** every cache key must be source-suffixed. The existing keys (`"fetch"`, `"classifier"`, `"analyzer"`, `"scorer"`, `"novelty"`) must NOT be re-used — they would collide between chains in the same day. Old cache files from v1 will be naturally ignored once the keys differ.

### 2. Per-source threshold is already implicit

`score_problems` already filters by `MIN_OPPORTUNITY_SCORE = 4.5`. That gives us the per-source threshold "for free" — no extra filtering step needed before merge.

### 3. Graceful degradation

Wrap each chain in its own `try / except` inside `run_pipeline`. If one source raises, log the failure and continue with the other source's results. If **both** chains fail, run the existing emergency notify and return exit code 1.

```python
try:
    trends_scored = _run_chain("trends")
except Exception as e:
    log(f"⚠️  Trends chain failed: {type(e).__name__}: {e}")
    trends_scored = []

try:
    reddit_scored = _run_chain("reddit")
except Exception as e:
    log(f"⚠️  Reddit chain failed: {type(e).__name__}: {e}")
    reddit_scored = []

if not trends_scored and not reddit_scored:
    _emergency_notify("Trend Engine: both sources produced zero results.", send_telegram)
    return 1
```

This satisfies verification steps 9 and 10 from the parent plan.

### 4. Merge

```python
from app.pipeline.merger import merge_and_dedupe

merged = merge_and_dedupe(trends_scored, reddit_scored)
log(f"Merged: {len(merged)} unique problems "
    f"({sum('trends' in p['sources'] for p in merged)} from Trends, "
    f"{sum('reddit' in p['sources'] for p in merged)} from Reddit)")
```

### 5. `apply_caps`

Add a new helper in `orchestrator.py`:

```python
def apply_caps(
    merged: list[ScoredProblem],
    max_trends: int = 4,
    max_reddit: int = 6,
) -> list[ScoredProblem]:
    """
    Cap output by source. Entries tagged with both sources count toward both caps.
    Input must already be sorted by opportunity_score descending (the merger does this).
    """
```

Algorithm (greedy, in score order):

```
trends_count = 0
reddit_count = 0
kept = []

for entry in merged:
    has_trends = "trends" in entry["sources"]
    has_reddit = "reddit" in entry["sources"]

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
```

Note: a dual-source entry requires **both** budgets to have headroom; if either is full, the entry is dropped. This matches the parent plan's wording that dual-source entries "count toward BOTH caps."

### 6. Final delivery + persistence

```python
capped = apply_caps(merged, max_trends=4, max_reddit=6)

save_pipeline_output(capped)
save_todays_problems(capped)
cached_stage("deliver", deliver, capped, send_telegram=send_telegram)
```

`save_todays_problems` is the history persistence used by novelty detection. Keep using it on the final capped set so novelty across days reflects what was actually delivered.

### 7. CLI flags unchanged

The `--no-send` and `--fresh` flags continue to work exactly as before. `--fresh` should clear all v2 cache keys (the existing `clear_todays_cache()` clears by day, which is naturally key-agnostic — verify this is still true).

### 8. Logging

Each chain should log its own stage progress, prefixed so you can tell them apart at a glance:

```
[2026-05-14 09:01:02] === Trends chain ===
[2026-05-14 09:01:02] Stage 0: Fetching trends...
...
[2026-05-14 09:01:30] === Reddit chain ===
[2026-05-14 09:01:30] Stage 0: Fetching Reddit posts...
```

Keep the existing pipeline header / footer / emergency-notify behavior.

## Acceptance criteria

- `python -m app.pipeline.orchestrator --no-send --fresh` runs end-to-end and prints the new merged briefing with no crashes.
- Cache files written for one day include all of: `fetch_trends.json`, `fetch_reddit.json`, `classifier_trends.json`, `classifier_reddit.json`, ..., `deliver.json` — no key collisions.
- If you wipe Reddit credentials in `.env` and re-run, the Trends chain still completes and produces a briefing; the Reddit failure is logged but not fatal.
- The reverse (wipe SerpApi key) is also non-fatal.
- A run with 8 qualifying Reddit problems and 7 qualifying Trends problems delivers exactly 6 Reddit + 4 Trends entries (plus any dual-source entries up to the joint cap).
- Re-running without `--fresh` skips already-cached stages for both chains.

## Out of scope

- Do NOT run the two chains concurrently — explicit non-goal in the parent plan ("keep it simple, run sequentially").
- Do NOT change FastAPI route behavior in `app/api/routes/pipeline.py` — that route already calls `run_pipeline`, and `run_pipeline`'s signature is unchanged.
- Do NOT touch `app/services/cache.py`, `app/services/history.py`, or `app/db/*`.
- Do NOT change the threshold or the geometric-mean math.
