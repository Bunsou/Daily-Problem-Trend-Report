# Task 02 — Implement the Reddit fetcher

**Status:** Not started
**Depends on:** task01 (settings + PRAW installed)
**Unblocks:** task06 (orchestrator needs a working fetcher to wire in)

## Goal

Add a Reddit ingestion path that returns post records in a shape the existing `classifier → analyzer → scorer → novelty` chain can consume, while preserving Reddit-specific context (body text, permalink, subreddit, comment count) for the analyzer.

## Files to touch

- **New:** `app/clients/reddit.py` — single shared PRAW `Reddit` instance (matches the existing `app/clients/gemini.py` / `app/clients/telegram.py` convention).
- **New:** `app/pipeline/reddit_fetcher.py` — fetching logic and `RedditEntry` TypedDict.

## Implementation steps

### 1. Create the shared PRAW client at `app/clients/reddit.py`

- Instantiate a single `praw.Reddit(...)` at module import time, mirroring how `app/clients/gemini.py` exposes `client`.
- Use **read-only mode** (no username/password). PRAW's read-only mode is the default when you instantiate with just `client_id`, `client_secret`, and `user_agent`.
- Pull credentials from `app.core.config.settings` — never `os.getenv` directly.
- Export the instance as `client` (matching the gemini client convention) so callers can `from app.clients.reddit import client`.

### 2. Define `RedditEntry` in `app/pipeline/reddit_fetcher.py`

The TypedDict must match the v2-plan schema exactly so downstream code that reads `query` / `countries` / `categories` keeps working:

```python
class RedditEntry(TypedDict):
    query: str             # the post title (treated as the "search query" downstream)
    countries: list[str]   # always ["reddit"] — placeholder so existing code paths work
    categories: list[str]  # subreddit name treated as category
    search_volume: str     # the post's upvote count, as a string
    related_queries: list[str]  # empty list — Reddit has no related queries
    post_body: str         # the full selftext (new field, Reddit-only)
    url: str               # the permalink
    subreddit: str         # source subreddit
    num_comments: int      # engagement signal
```

### 3. Hardcoded subreddit list

Define at module scope:

```python
DEFAULT_SUBREDDITS = [
    "smallbusiness",
    "sweatystartup",
    "Entrepreneur",
    "freelance",
    "webdev",
    "SaaS",
    "ITManagers",
    "AskHR",
    "Accounting",
    "ecommerce",
]
```

### 4. `fetch_reddit_posts() -> list[RedditEntry]`

Behavior:

- Iterate over `DEFAULT_SUBREDDITS`. For each:
  - Call `client.subreddit(name).new(limit=50)`.
  - Keep only posts created in the **last 24 hours** (compare `submission.created_utc` against `time.time() - 86400`).
  - Skip posts where `selftext` is empty, `"[removed]"`, or `"[deleted]"` (link-only posts have no problem description).
  - Map each surviving submission into a `RedditEntry`.
- **Deduplicate by `submission.id`** across all subreddits — crossposts can surface the same post in r/SaaS and r/Entrepreneur; keep one (first wins).
- **Per-subreddit error isolation:** if one subreddit raises (rate limit, banned, network blip), `print` a clear log line naming the subreddit and the error type, then continue to the next subreddit. Do NOT let one failure abort the whole fetch.
- **Politeness sleep:** `time.sleep(1.5)` *between* subreddit fetches (not before the first, not after the last).

### 5. Logging style

Use `print` for logs (matches the rest of the codebase — do not introduce `logging`). At minimum, emit:
- A start line naming the count of subreddits being polled.
- A per-subreddit summary like `r/SaaS: 12 new posts in window, 8 with selftext`.
- A final line with the total returned and the number of cross-subreddit duplicates removed.

### 6. `__main__` smoke entry point (optional but recommended)

Mirror the dev-mode pattern in `app/pipeline/fetcher.py` — when run as `python -m app.pipeline.reddit_fetcher`, print the first few entries' titles, subreddits, and upvote counts so the developer can sanity-check credentials and connectivity without running the full pipeline.

## Acceptance criteria

- `from app.pipeline.reddit_fetcher import fetch_reddit_posts, RedditEntry, DEFAULT_SUBREDDITS` works.
- Running `python -m app.pipeline.reddit_fetcher` against real credentials prints a non-empty list of recent posts and respects the 24-hour window.
- A deliberately corrupted credential set fails fast with a clear error (PRAW raises on the first API call).
- Killing the network mid-run for one subreddit does NOT abort the whole fetch — the function returns what it gathered from the surviving subreddits.
- No PRAW import lives outside `app/clients/reddit.py` (the fetcher imports `client`, not `praw`).

## Out of scope

- Do NOT call the classifier / analyzer / scorer from this file — pure fetcher only.
- Do NOT touch the existing `fetch_trends` in `app/pipeline/fetcher.py`.
- Do NOT introduce async — keep it synchronous, matching v1.
- Do NOT add a `BaseFetcher` abstraction or any shared interface between Trends and Reddit fetchers (explicit non-goal in the parent plan).
