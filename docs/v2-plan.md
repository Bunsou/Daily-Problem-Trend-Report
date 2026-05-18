---
## Final design check (private to me, then prompt below)

The shape of v2 is:
  - Two parallel ingestion paths (Reddit via PRAW, Trends via existing SerpApi)
  - Each runs through filter → analyzer → scorer → novelty independently
  - Final delivery merges, dedupes across sources, caps at 4 trends + 6 Reddit
  - One analyzer file with a `source` parameter that adjusts framing
  - Trends analyzer mode hardcodes exclusion of legal/medical/hospital/pharmaceutical
  - Buyer test stays as internal scoring rigor; new `potential_customer` field for display
  - Briefing format trimmed: no solutions, no buyer_test rationale shown
  - Dedup keeps a single entry with combined source attribution
  - Threshold 4.5 applied per source before merge

I'll spell each of these out explicitly so Claude Code can't guess wrong. Here's the prompt:
---

````markdown
# Task: Build v2 of the Trend Engine pipeline with Reddit as a second data source

## Context

This is a daily Python cron pipeline that currently fetches Google Trends, processes them through AI stages, and delivers a Telegram briefing. v1 is shipped and working. v2 adds Reddit as a parallel data source and refines the output format. The existing code is well-structured with single-responsibility modules; preserve that style.

## Scope: What changes and what doesn't

**IN SCOPE:**

- Add a Reddit fetcher using PRAW
- Modify the analyzer to handle both Trends and Reddit data via a `source` parameter
- Run two parallel mini-pipelines (one per source), each going through filter → classifier → analyzer → scorer → novelty
- Merge results at the delivery stage with deduplication
- Trim the briefing format (remove solutions, remove buyer_test display, add potential_customer)
- Apply hardcoded category exclusion (legal/medical/hospital/pharmaceutical) to Trends path only
- Update the deliverer to format the new briefing structure
- Update env vars, requirements.txt, README

**OUT OF SCOPE — DO NOT TOUCH:**

- Do NOT touch the database layer (`db.py`, `history.py`, Alembic migrations)
- Do NOT touch the Telegram client (`telegram_client.py`)
- Do NOT touch the pipeline stage caching (`pipeline_cache.py`)
- Do NOT change novelty detection logic in `novelty.py` other than ensuring it correctly handles both sources
- Do NOT introduce async/await patterns; keep the codebase synchronous
- Do NOT add new abstraction layers (no "BaseFetcher", no "SourceStrategy" classes)
- Do NOT change how the FastAPI app (`app.py`) exposes endpoints

## Architectural decisions (already made — do not deviate)

1. **Reddit access:** PRAW (Python Reddit API Wrapper), read-only mode, free tier (100 QPM is sufficient)
2. **Reddit post selection:** New posts from the last 24 hours per subreddit, not "hot" or "top"
3. **Parallel pipelines:** Each source has its own fetcher → category_filter → classifier → analyzer → scorer → novelty chain. The two chains run sequentially (not concurrently — keep it simple). Results merge at delivery.
4. **Per-source thresholding:** Each source's results are filtered by `opportunity_score >= 4.5` before merging.
5. **Caps after merge:** Max 4 Trends entries + max 6 Reddit entries = max 10 total. If a source produces fewer qualifying entries than its cap, the briefing is shorter.
6. **Deduplication:** After both sources produce scored problems, deduplicate by semantic similarity (use a single AI call). Entries that appear in both sources are merged into one entry with combined source attribution ("Both Reddit and Trends"). The higher score wins for the displayed score.
7. **One analyzer file, two modes:** Pass `source: str` parameter to `analyze_trends()`. Core rules stay in a shared prompt body; source-specific framing is appended.
8. **Trends category exclusion:** Hardcoded list in the analyzer module: legal, medical, hospital, pharmaceutical, medicine. Only applied when source=="trends". Reddit is unfiltered.
9. **Two display fields the scorer must produce:**
   - `buyer_test`: keep as is — used for internal scoring rigor, not displayed
   - `potential_customer`: new field, 1-2 sentences naming the buyer persona, displayed in briefing

## Reddit subreddit list (hardcoded default)

```python
DEFAULT_SUBREDDITS = [
    "smallbusiness",       # owners describing operational pain
    "sweatystartup",       # service-business operators
    "Entrepreneur",        # broad founder pain
    "freelance",           # solo operator problems
    "webdev",              # tech-specific implementation pain
    "SaaS",                # B2B software pain
    "ITManagers",          # enterprise IT pain
    "AskHR",               # people management problems
    "Accounting",          # finance profession pain
    "ecommerce",           # online retail operator pain
]
```
````

## Files to create

1. **`reddit_fetcher.py`** — fetches new posts from configured subreddits over the last 24 hours via PRAW. Returns a list of dicts in the same shape as the existing `TrendEntry` TypedDict where applicable, plus Reddit-specific fields:

   ```python
   class RedditEntry(TypedDict):
       query: str           # the post title (treated as the "search query" by downstream code)
       countries: list[str] # always ["reddit"] — placeholder so existing code paths work
       categories: list[str] # subreddit name treated as category
       search_volume: str   # the post's upvote count as a string
       related_queries: list[str]  # empty list — Reddit doesn't have this
       post_body: str       # the full selftext of the post (new field, Reddit only)
       url: str             # the permalink (for traceability)
       subreddit: str       # the source subreddit
       num_comments: int    # signal of engagement
   ```

   The fetcher should:
   - Read Reddit credentials from env vars: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`
   - Use PRAW in read-only mode (no username/password needed)
   - Iterate `subreddit.new(limit=50)` for each subreddit and filter posts to those created in the last 24 hours
   - Deduplicate by post ID across subreddits (a post in r/SaaS might also appear in r/Entrepreneur via crossposts; keep one)
   - Skip posts where `selftext` is empty (link-only posts have no problem description) or marked as "[removed]" / "[deleted]"
   - Handle errors gracefully — if one subreddit fails, log and continue with the rest
   - Add `time.sleep(1.5)` between subreddit fetches to be polite to Reddit's API even when under rate limit

2. **No new `category_filter` needed for Reddit** — subreddit selection IS the category filter. Skip this stage when source=="reddit".

## Files to modify

1. **`config.py`** — add three new env vars:

   ```python
   REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
   REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
   REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "trend-engine-v2")
   ```

   Add `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` to the existing validation block. `REDDIT_USER_AGENT` has a default so it's optional.

2. **`analyzer.py`** — modify `analyze_trends()` to take a new parameter `source: str` (values: "trends" or "reddit"). Adjust prompt building:
   - Extract the shared prompt rules into a constant `SHARED_ANALYZER_RULES` containing:
     - What counts as a real problem
     - The output JSON schema (`problem_name`, `description`, `evidence`, `category`, `countries`)
     - The "when to return nothing" rule
   - For `source=="trends"`, append a section instructing:
     - Input is short search query strings with metadata
     - Infer problems from query patterns and related searches
     - **HARDCODED EXCLUSION:** "Additionally, exclude any problems in these domains: legal, law, medical, hospital, pharmaceutical, medicine. Do not extract problems from trends in these categories even if they appear to be real problems. They are out of scope for this analysis."
   - For `source=="reddit"`, append a section instructing:
     - Input is Reddit posts with title and body text (long-form descriptions)
     - Quote directly from post bodies when extracting evidence
     - Each post's title is generally the problem statement; the body provides context
     - Treat post engagement (upvotes, comments) as signal strength
     - Use the subreddit name as a category hint (e.g., posts from r/Accounting are likely finance/accounting domain)
   - The function signature becomes:
     ```python
     def analyze_trends(entries: list[dict], source: str) -> list[Problem]: ...
     ```

3. **`scorer.py`** — add `potential_customer` to the `ScoredProblem` TypedDict and the prompt output schema. The new field should be 1-2 sentences naming the buyer persona with minimal context (NOT the full buyer_test rationale).

   Update the scorer prompt:
   - Keep the existing buyer test mechanism (it forces rigor)
   - In addition, instruct the AI to also produce `potential_customer` — a short, display-friendly version that just names the buyer. Examples:
     - Good: "Personal injury law firms — they already buy leads via Google Ads."
     - Good: "Small business HR managers handling first-time disputes."
     - Bad: "Anyone interested in legal services."
     - Bad: A full sentence repeating the buyer test rationale.

   The output JSON must include both `buyer_test` (existing) and `potential_customer` (new).

4. **`main.py`** — restructure the orchestration. Replace the single linear flow with two parallel chains followed by a merge step. Pseudocode:

   ```
   trends_results = run_chain(source="trends")
   reddit_results = run_chain(source="reddit")
   merged = merge_and_dedupe(trends_results, reddit_results)
   capped = apply_caps(merged, max_trends=4, max_reddit=6)
   deliver(capped, send_telegram=send_telegram)
   ```

   Where `run_chain(source)`:
   - For trends: calls existing fetch → category_filter → classifier → analyzer (with source="trends") → scorer → novelty
   - For reddit: calls reddit_fetcher → (skip category_filter) → classifier → analyzer (with source="reddit") → scorer → novelty

   Each chain wraps stage calls in `cached_stage()` as before. Cache keys must include the source — e.g., `cached_stage("classifier_trends", ...)` and `cached_stage("classifier_reddit", ...)`. Otherwise the two chains would clobber each other's cache.

5. **New module `merger.py`** — handles the cross-source dedup and merging:

   ```python
   def merge_and_dedupe(
       trends_problems: list[ScoredProblem],
       reddit_problems: list[ScoredProblem],
   ) -> list[ScoredProblem]: ...
   ```

   Behavior:
   - Tag each problem with its source: add a `sources` field (list of strings, e.g., `["trends"]`, `["reddit"]`, or `["trends", "reddit"]` after dedup)
   - Use a single Gemini call to identify semantically duplicate problems across the two lists
   - When duplicates are found, merge into one entry:
     - Keep the higher-scored version's content
     - Combine `sources` to `["trends", "reddit"]`
     - Combine `countries` lists
   - Return the merged list, NOT yet capped

   The dedup AI prompt should be tight and focused: given two lists of problems, identify pairs that represent the same underlying pain. Return a JSON list of `{trends_index, reddit_index}` pairs. Process duplicates by removing the lower-scored entry and tagging the survivor as `sources=["trends", "reddit"]`.

   On dedup AI failure, return the simple concatenation of both lists with each entry tagged with only its original source. Pipeline must not crash.

6. **`main.py` again** — add `apply_caps(merged, max_trends, max_reddit)`:
   - Iterate through the merged list (sorted by opportunity_score desc)
   - Count entries by source: entries with sources containing "trends" count toward the trends cap, same for reddit
   - Entries marked `sources=["trends", "reddit"]` count toward BOTH caps (they're showing in both source budgets)
   - Stop adding entries once either cap is reached for further entries of that source type
   - Return the capped list

7. **`deliverer.py`** — modify `_format_single_problem()` to match the new spec. New layout per problem:

   ```
   1. 🆕 [NEW] Problem name [from: trends, reddit]
      Category: legal  •  Score: 7.8
      Demand: 8  •  Monetization: 9  •  Buildability: 7

      💡 [key insight]

      🎯 Potential customer: [potential_customer]

      📝 [description]

      📌 [novelty_note]
   ```

   Remove from the format:
   - The `🎯 Buyer test:` line (the long buyer_test rationale)
   - The `🛠 Solutions:` section and all bullet points beneath it

   Add to the format:
   - A "[from: SOURCES]" tag in the title line, where SOURCES is a comma-separated list from the `sources` field
   - The `🎯 Potential customer:` line using the new `potential_customer` field

   Update the briefing header too: `📊 Daily Opportunity Radar — Apr 26, 2026` then `X opportunities today (Y from Trends, Z from Reddit)`.

8. **`requirements.txt`** — add:

   ```
   praw>=7.7,<8.0
   ```

9. **`.env` example / README** — document the new env vars:
   - `REDDIT_CLIENT_ID`
   - `REDDIT_CLIENT_SECRET`
   - `REDDIT_USER_AGENT` (optional, defaults to "trend-engine-v2")

   Include step-by-step Reddit app setup instructions in the README:
   1. Go to https://www.reddit.com/prefs/apps
   2. Click "Create app" at the bottom of the page
   3. Choose "script" as the app type
   4. Name: "trend-engine-v2" (or anything you want)
   5. Set redirect URI to `http://localhost:8080` (required but unused for script apps)
   6. Click "Create app"
   7. The 14-character string under the app name is your `REDDIT_CLIENT_ID`
   8. The "secret" field is your `REDDIT_CLIENT_SECRET`
   9. For `REDDIT_USER_AGENT`, use the format: `script:trend-engine-v2:v1.0 (by /u/your_reddit_username)`

10. **For Render deployment** — note in README: add `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, and `REDDIT_USER_AGENT` to the Render service's environment variables alongside the existing ones.

## Required behavior of the new deliverer header

For an example output with 2 trends entries and 5 reddit entries, including 1 deduplicated entry that came from both:

```
📊 Daily Opportunity Radar — Apr 26, 2026

7 qualifying opportunities today (3 from Trends, 6 from Reddit)
────────────────────────────────────────

1. 🆕 [NEW] Filing flight cancellation claims [from: trends, reddit]
   ...
```

Note: the entry counts in the header reflect the source-tagged count (sources with two tags count toward both, just like in the cap logic).

## Verification steps the implementation must enable

After your changes, the following must work:

1. Run `python main.py --no-send --fresh` — should successfully fetch from both Reddit and Trends, run all stages for each, merge, dedupe, and deliver. No crashes.
2. Briefing in Telegram (or printed) must follow the new format: no solutions, no buyer test rationale shown, with potential_customer field present, source attribution tag in title.
3. Trends entries about legal/medical topics must NOT appear in output (verify by checking a day's output).
4. Reddit entries about legal/medical topics ARE allowed (they're not filtered).
5. Cap behavior: if Reddit produces 8 qualifying problems, only 6 appear; if Trends produces 7, only 4 appear.
6. Dedup behavior: if both sources surface the same problem, one entry appears with `[from: trends, reddit]` attribution.
7. Database/history continues to work — novelty detection should function across both sources.
8. Pipeline cache works per source (stages can independently be cached and resumed).
9. If Reddit is unavailable (bad credentials, network error), pipeline still completes with Trends-only results.
10. If Trends is unavailable, pipeline still completes with Reddit-only results.

## Code style requirements

- Match existing patterns: TypedDicts where existing code uses them, type hints throughout, docstrings on public functions.
- Use `print` for logging (matching existing style); no introduction of `logging` module.
- Match existing import organization (stdlib, third-party, local — separated by blank lines).
- Keep error messages helpful and specific.
- Update existing module docstrings where behavior is meaningfully changed.

## Final reminder

The goal is to add Reddit as a parallel data source and refine the output format, with minimal disruption to working v1 infrastructure (database, cache, retry logic, FastAPI wrapper, Telegram delivery). The existing pipeline stages are battle-tested; treat them with respect. Most of your edits will be additive (new files, new function parameters) rather than rewriting working code.

If you encounter ambiguity that isn't resolved by these instructions, **stop and ask** rather than guessing. The previous v1 implementation was done well; v2 should preserve that quality.

```

---

## A few notes about this prompt before you send it

**The `RedditEntry` schema design.** I deliberately mapped Reddit data into a shape compatible with the existing `TrendEntry`. The `query` field holds the post title, `categories` holds the subreddit name, and so on. This lets the existing classifier/analyzer/scorer chain reuse most logic without major rewriting. The Reddit-specific fields (`post_body`, `url`, `subreddit`, `num_comments`) are additive — they enrich the data for the analyzer prompt without breaking anything downstream.

**Why I added the merger as a separate file.** The merge-and-dedupe step is a real piece of logic with its own AI call and its own failure mode. Putting it in `main.py` would bloat the orchestrator. Giving it its own file keeps the responsibility clear.

**Cache key isolation.** I called out explicitly that each cached stage needs a per-source key, otherwise the Reddit classifier output would overwrite the Trends classifier output on the same day. This is the kind of subtle bug that's annoying to debug.

**The "stop and ask" line at the bottom.** This is important — it tells Claude Code not to invent solutions when the spec is silent. With v2 having more moving parts than v1, ambiguities are more likely. Better to get questions than guesses.

**The "process duplicates by removing the lower-scored entry" detail.** This is a small but real implementation choice. Without specifying it, Claude Code might decide to average the scores, or keep both, or do something else odd. Explicit instruction prevents weird choices.

---

## What to expect when Claude Code finishes

Run through the 10 verification steps in order. The ones most likely to surface issues:

- **Step 3** (Trends legal exclusion): manually look at a day's output and confirm no legal/medical entries from the Trends source
- **Step 6** (dedup behavior): you might need to wait for a day where genuinely overlapping problems surface from both sources
- **Step 9 and 10** (graceful degradation): temporarily corrupt one source's credentials and verify the pipeline still produces output from the other

If Claude Code makes any decisions that don't match the spec, point them out specifically and ask for corrections rather than accepting the diff blindly.

Once you've verified v2 is solid, run it daily for a week and see if the output quality is genuinely better than v1. That's the real test of whether the data-source pivot was worth the effort. Report back with what you see — I'd be curious to know whether Reddit gives you the signal density we hoped for.
```
