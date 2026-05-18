"""
Reddit fetcher — v2 secondary data source.

Pulls new posts from a hardcoded list of operator/founder/professional
subreddits over the last 24 hours and returns them in a shape compatible with
the existing classifier → analyzer → scorer → novelty chain.

Reddit-specific fields (`post_body`, `url`, `subreddit`, `num_comments`) are
additive — they enrich the analyzer prompt without breaking downstream code
that only reads the v1 `TrendEntry`-shaped fields.

Run as a smoke test:

    python -m app.pipeline.reddit_fetcher
"""
import logging
import time
from datetime import datetime, timezone
from typing import TypedDict

import requests

logger = logging.getLogger(__name__)

REDDIT_USER_AGENT = "trend-engine/2.0 (personal project; read-only public subreddits)"
REDDIT_BASE_URL = "https://www.reddit.com"
SLEEP_BETWEEN_SUBREDDITS = 1.5
RETRY_SLEEP_SECONDS = 5
REQUEST_TIMEOUT_SECONDS = 10
POSTS_PER_SUBREDDIT = 50
LOOKBACK_HOURS = 24

# Operator / founder / professional subreddits where people describe real pain.
# Subreddit selection IS the category filter for the Reddit chain — there is no
# separate category_filter stage downstream.
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


class RedditEntry(TypedDict):
    """A single Reddit post mapped onto a TrendEntry-compatible shape."""
    query: str             # the post title — treated as the "search query" by downstream code
    countries: list[str]   # always ["reddit"] — placeholder so existing code paths work
    categories: list[str]  # subreddit name treated as category
    search_volume: str     # the post's upvote count, as a string
    related_queries: list[str]  # always [] — Reddit has no related-queries concept
    post_body: str         # the full selftext (new field, Reddit-only)
    url: str               # the permalink
    subreddit: str         # source subreddit name
    num_comments: int      # engagement signal


def fetch_reddit_posts(subreddits: list[str] | None = None) -> list[RedditEntry]:
    """
    Fetch new posts from the past 24 hours across configured subreddits.
    Returns RedditEntry objects deduplicated by post ID.
    """
    if subreddits is None:
        subreddits = DEFAULT_SUBREDDITS

    cutoff = datetime.now(timezone.utc).timestamp() - (LOOKBACK_HOURS * 3600)

    seen_ids: set[str] = set()
    entries: list[RedditEntry] = []
    duplicates_skipped = 0

    logger.info("Reddit fetcher: polling %d subreddit(s) for new posts in the last 24h...", len(subreddits))
    print(f"Reddit fetcher: polling {len(subreddits)} subreddit(s) "
          f"for new posts in the last 24h...")

    for i, name in enumerate(subreddits):
        if i > 0:
            time.sleep(SLEEP_BETWEEN_SUBREDDITS)

        raw_posts = _fetch_one_subreddit(name)

        in_window = 0
        kept = 0

        for post in raw_posts:
            if post.get("created_utc", 0) < cutoff:
                continue

            in_window += 1

            post_id = post.get("id") or post.get("permalink", "")
            if post_id in seen_ids:
                duplicates_skipped += 1
                continue

            body = (post.get("selftext") or "").strip()
            if not body or body in ("[removed]", "[deleted]"):
                continue

            if post_id:
                seen_ids.add(post_id)
            entries.append(_post_to_entry(post))
            kept += 1

        logger.info("r/%s: %d new in window, %d with selftext", name, in_window, kept)
        print(f"  r/{name}: {in_window} new in window, {kept} with selftext")

    logger.info(
        "Reddit fetcher: returned %d unique post(s); skipped %d crosspost duplicate(s).",
        len(entries), duplicates_skipped,
    )
    print(f"Reddit fetcher: returned {len(entries)} unique post(s); "
          f"skipped {duplicates_skipped} crosspost duplicate(s).")

    return entries


def _fetch_one_subreddit(name: str) -> list[dict]:
    """
    Fetch raw post dicts from one subreddit's /new.json endpoint.
    Returns [] on any failure. Never raises.
    """
    url = f"{REDDIT_BASE_URL}/r/{name}/new.json?limit={POSTS_PER_SUBREDDIT}"
    headers = {"User-Agent": REDDIT_USER_AGENT}

    def _do_request() -> requests.Response:
        return requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)

    try:
        resp = _do_request()

        if resp.status_code in (429, 503):
            logger.warning("r/%s: got %d — sleeping %ds then retrying", name, resp.status_code, RETRY_SLEEP_SECONDS)
            time.sleep(RETRY_SLEEP_SECONDS)
            try:
                resp = _do_request()
            except requests.RequestException as e:
                logger.error("r/%s: retry failed (%s) — skipping", name, e)
                return []

            if resp.status_code != 200:
                logger.error("r/%s: retry returned %d — skipping", name, resp.status_code)
                return []

        if resp.status_code == 403:
            logger.warning("r/%s: blocked (403) — skipping", name)
            return []

        if resp.status_code != 200:
            snippet = resp.text[:200] if resp.text else ""
            logger.error("r/%s: unexpected status %d — %s", name, resp.status_code, snippet)
            return []

        data = resp.json()
        children = data.get("data", {}).get("children", [])
        return [child["data"] for child in children]

    except requests.RequestException as e:
        logger.error("r/%s: network error (%s) — skipping", name, e)
        return []


def _post_to_entry(post: dict) -> RedditEntry:
    """Convert a raw Reddit post dict to a RedditEntry."""
    return {
        "query": post.get("title", ""),
        "countries": ["reddit"],
        "categories": [post.get("subreddit", "")],
        "search_volume": str(post.get("score", 0)),
        "related_queries": [],
        "post_body": post.get("selftext", ""),
        "url": f"{REDDIT_BASE_URL}{post.get('permalink', '')}",
        "subreddit": post.get("subreddit", ""),
        "num_comments": post.get("num_comments", 0),
    }


if __name__ == "__main__":
    posts = fetch_reddit_posts()

    print(f"\nFetched {len(posts)} Reddit posts:\n")
    for i, p in enumerate(posts[:10], start=1):
        print(f"{i}. [r/{p['subreddit']}] ▲{p['search_volume']}  💬{p['num_comments']}")
        print(f"   {p['query']}")
        print(f"   {p['url']}")
        print()

    if len(posts) > 10:
        print(f"... and {len(posts) - 10} more posts")
