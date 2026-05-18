"""
Stage 2 analyzer: identify real problems from pre-filtered candidates.

Works for both Google Trends search entries and Reddit posts. The shared
"what counts as a real problem" rules live in `SHARED_ANALYZER_RULES`; the
source-specific framing (input shape, Trends-only category exclusion) is
appended per call via the `source` parameter on `analyze_trends`.
"""
import json
import logging
import time
from typing import TypedDict

from app.clients.gemini import client as _client

logger = logging.getLogger(__name__)


class Problem(TypedDict):
    """A real problem identified from a trending search or Reddit post."""
    problem_name: str
    description: str
    evidence: list[str]
    category: str
    source_trends: list[str]  # backward-compat alias for evidence; scorer reads this
    countries: list[str]


MODEL_NAME = "gemini-2.5-flash-lite"

# Reddit selftexts can be very long. Truncate per-entry in the rendered prompt
# to keep total prompt size manageable while preserving enough context to
# extract real problems.
MAX_POST_BODY_CHARS = 1500

# Maximum entries per analyzer API call. Reddit sends 200+ posts in a run;
# sending them all at once produces 100+ "problems" (model ignores the 3-7
# guideline when every post is business-relevant) and risks a context-length
# timeout. Batching keeps each call within the intended output range.
ANALYZER_BATCH_SIZE = 50

# Politeness pause between batched analyzer calls.
ANALYZER_BATCH_SLEEP = 1.0


SHARED_ANALYZER_RULES = """You are a problem-discovery analyst. Your ONLY job is to identify entries that demonstrate active problem-solving behavior — not topical interest, not curiosity, not news consumption.

# The single rule that governs everything

An entry qualifies as a "problem" ONLY if the input itself demonstrates that the person is **actively trying to solve, fix, choose, find, or understand how to do something**.

This means the language must contain solution-seeking intent. Examples:

✅ QUALIFIES (clear solution-seeking):
- "how to dispute a denied insurance claim"
- "best way to consolidate student loans"
- "find lawyer for car accident"
- "alternatives to [expensive software]"
- "why is my [thing] doing [bad outcome]"

❌ DOES NOT QUALIFY (topical interest, not problem-solving):
- "Pfizer stock" — interest in a company, no pain
- "Trump immigration" — political news consumption
- "iPhone 17" — product curiosity
- "London weather" — informational lookup
- "San Diego Zoo" — entertainment/leisure browsing
- "[celebrity name]" — gossip
- Company names, person names, place names, event names alone

# What this means in practice

Most entries do not qualify. That is correct and expected. A typical good output is **3 to 7 sharp problems**, not 15 vague ones. If you find yourself "inferring" a problem from an entry that's actually just topical interest, STOP. That's the failure mode this prompt exists to prevent.

You are NOT trying to maximize output count. You are trying to maximize output quality. Returning 4 sharp problems is far better than 12 mushy ones.

# How to extract a qualifying problem

For each cluster of qualifying entries, extract:

1. **problem_name** (max 8 words): The specific pain, framed as a problem people face. NOT a category. NOT a topic.
   - Good: "Disputing rejected health insurance claims"
   - Bad: "Health-related concerns" or "Personal wellness management"

2. **description** (one sentence): What is the actual struggle? What action are people trying to take and what's blocking them?
   - Good: "Patients whose claims were denied are searching for templates and steps to file appeals before deadlines expire."
   - Bad: "People are interested in their health and managing wellness."

3. **evidence**: List 2-4 source entries from the input that DIRECTLY demonstrate solution-seeking. If you can't find at least 2 entries with explicit solution-seeking language, this is not a real problem — skip it.

4. **category**: one of: health, finance, tech, education, housing, legal, career, relationships, lifestyle, other

5. **countries**: country codes from the source entries

# When to return nothing

If fewer than 3 entries in the entire input demonstrate clear solution-seeking, return an empty array []. This is a valid and correct output. Manufacturing problems from topical interest is the worst thing you can do."""


TRENDS_SOURCE_GUIDANCE = """# Source: Google Trends

- Input is short search query strings with country and category metadata.
- Infer problems from query patterns and related searches.

Additionally, exclude any problems in these domains: legal, law, medical, hospital, pharmaceutical, medicine. Do not extract problems from trends in these categories even if they appear to be real problems. They are out of scope for this analysis."""


REDDIT_SOURCE_GUIDANCE = """# Source: Reddit

- Input is Reddit posts with title and body text (long-form descriptions).
- Quote directly from post bodies when extracting evidence — short verbatim phrases beat paraphrases.
- Each post's title is generally the problem statement; the body provides context and corroboration.
- Treat post engagement (upvotes, comments) as signal strength — heavily upvoted posts represent widespread pain.
- Use the subreddit name as a category hint (e.g., posts from r/Accounting are likely finance/accounting domain)."""


OUTPUT_FORMAT_BLOCK = """# Output format
Return ONLY a JSON array. No markdown fences, no commentary.

Example of GOOD output:
[
  {
    "problem_name": "Consolidating federal student loans",
    "description": "Recent graduates are searching for step-by-step guidance on consolidating multiple federal loans to lower their monthly payments.",
    "evidence": ["how to consolidate student loans", "best student loan consolidation 2026"],
    "category": "finance",
    "countries": ["US", "GB"]
  }
]"""


def _render_trends_entries(entries: list[dict]) -> str:
    """Render Trends entries as short bulleted lines with country/category metadata."""
    lines = []
    for t in entries:
        line = f"- \"{t['query']}\" (in: {', '.join(t['countries'])})"

        if t.get("categories"):
            line += f" [{', '.join(t['categories'])}]"

        if t.get("related_queries"):
            related = ", ".join(t["related_queries"][:3])
            line += f"\n  Related searches: {related}"

        lines.append(line)
    return "\n\n".join(lines)


def _render_reddit_entries(entries: list[dict]) -> str:
    """Render Reddit entries as title + truncated body with engagement signal."""
    lines = []
    for r in entries:
        body = (r.get("post_body") or "").strip()
        if len(body) > MAX_POST_BODY_CHARS:
            body = body[:MAX_POST_BODY_CHARS].rstrip() + "..."

        upvotes = r.get("search_volume") or "0"
        comments = r.get("num_comments", 0)
        subreddit = r.get("subreddit", "unknown")

        line = f"- r/{subreddit} (▲{upvotes}, 💬{comments}): \"{r['query']}\""
        if body:
            line += f"\n  Body: {body}"
        lines.append(line)
    return "\n\n".join(lines)


def build_prompt(entries: list[dict], source: str) -> str:
    """Assemble the analyzer prompt for the given source."""
    if source == "trends":
        framing = TRENDS_SOURCE_GUIDANCE
        input_block = _render_trends_entries(entries)
    elif source == "reddit":
        framing = REDDIT_SOURCE_GUIDANCE
        input_block = _render_reddit_entries(entries)
    else:
        raise ValueError(
            f"Unknown source: {source!r}. Expected 'trends' or 'reddit'."
        )

    return (
        f"{SHARED_ANALYZER_RULES}\n\n"
        f"{framing}\n\n"
        f"# Today's {source} data to analyze\n{input_block}\n\n"
        f"{OUTPUT_FORMAT_BLOCK}"
    )


def _parse_problems(raw_text: str) -> list[Problem]:
    """Parse and normalize a raw Gemini JSON response into a list of Problems."""
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    problems = json.loads(raw_text)

    if not isinstance(problems, list):
        raise ValueError(f"Expected list, got {type(problems)}")

    for problem in problems:
        # Backward compat: scorer expects source_trends.
        if "evidence" in problem and "source_trends" not in problem:
            problem["source_trends"] = problem["evidence"]

    return problems


def _analyze_batch(entries: list[dict], source: str) -> list[Problem]:
    """
    Send one batch of entries to Gemini and return extracted problems.
    Retries once on any failure. Returns [] if both attempts fail — never raises.
    """
    prompt = build_prompt(entries, source)

    for attempt in range(2):
        raw_text = ""
        try:
            response = _client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
            )
            raw_text = (response.text or "").strip()
            return _parse_problems(raw_text)

        except json.JSONDecodeError as e:
            logger.warning(
                "Analyzer: JSON parse error (attempt %d/2): %s | raw snippet: %s",
                attempt + 1, e, raw_text[:300],
            )
            if attempt == 0:
                time.sleep(ANALYZER_BATCH_SLEEP)
            else:
                print(f"Failed to parse AI response as JSON: {e}")

        except Exception as e:
            logger.warning("Analyzer: error (attempt %d/2): %s", attempt + 1, e)
            if attempt == 0:
                time.sleep(ANALYZER_BATCH_SLEEP)
            else:
                print(f"Error analyzing entries: {e}")

    return []


def analyze_trends(entries: list[dict], source: str) -> list[Problem]:
    """
    Stage 2 analyzer: deep grouping and classification of pre-filtered entries.

    Large inputs are automatically split into batches of ANALYZER_BATCH_SIZE
    and processed in sequence. Results from all batches are merged.

    Args:
        entries: Trends entries (TrendEntry shape) or Reddit entries
            (RedditEntry shape). Both are accepted as plain dicts.
        source: Which data source the entries came from. Must be "trends" or
            "reddit". Determines prompt framing and input rendering.

    Returns:
        A list of Problem dicts. Empty if nothing qualifies.

    Raises:
        ValueError: If source is not "trends" or "reddit".
    """
    if source not in ("trends", "reddit"):
        raise ValueError(
            f"Unknown source: {source!r}. Expected 'trends' or 'reddit'."
        )

    if not entries:
        print(f"No {source} entries to analyze.")
        return []

    if len(entries) <= ANALYZER_BATCH_SIZE:
        return _analyze_batch(entries, source)

    # Split into batches to keep each Gemini call within a manageable context
    # window and to let the model respect its own "3-7 problems" guideline.
    total_batches = (len(entries) + ANALYZER_BATCH_SIZE - 1) // ANALYZER_BATCH_SIZE
    logger.info(
        "Analyzer: %d %s entries → %d batches of ≤%d",
        len(entries), source, total_batches, ANALYZER_BATCH_SIZE,
    )
    print(f"  Analyzer: splitting {len(entries)} entries into {total_batches} batches...")

    all_problems: list[Problem] = []
    for i in range(0, len(entries), ANALYZER_BATCH_SIZE):
        batch_num = i // ANALYZER_BATCH_SIZE + 1
        batch = entries[i : i + ANALYZER_BATCH_SIZE]
        logger.info("Analyzer: batch %d/%d (%d entries)", batch_num, total_batches, len(batch))
        print(f"    Batch {batch_num}/{total_batches}: {len(batch)} entries...", end=" ", flush=True)

        problems = _analyze_batch(batch, source)
        print(f"{len(problems)} problems found.")
        all_problems.extend(problems)

        if i + ANALYZER_BATCH_SIZE < len(entries):
            time.sleep(ANALYZER_BATCH_SLEEP)

    logger.info("Analyzer: %d total problems across all batches", len(all_problems))
    return all_problems


if __name__ == "__main__":
    from app.pipeline.fetcher import fetch_trends
    from app.pipeline.category_filter import filter_by_category
    from app.pipeline.classifier import classify_trends

    print("Stage 0: Fetching raw trends...")
    trends = fetch_trends()
    print(f"  Raw: {len(trends)}")

    print("\nStage 1a: Category filtering...")
    trends = filter_by_category(trends)
    print(f"  After category filter: {len(trends)}")

    print("\nStage 1b: AI classifier...")
    trends = classify_trends(trends)
    print(f"  After classifier: {len(trends)}")

    print(f"\nStage 2: Deep analysis on {len(trends)} candidates...\n")
    problems = analyze_trends(trends, source="trends")

    print(f"Identified {len(problems)} real problems:\n")
    for i, p in enumerate(problems, start=1):
        print(f"{i}. {p['problem_name']} [{p['category']}]")
        print(f"   {p['description']}")
        print(f"   Countries: {', '.join(p['countries'])}")
        print(f"   From trends: {p['source_trends']}\n")
