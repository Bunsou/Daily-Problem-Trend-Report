"""
Cross-source merger and semantic deduplicator for the v2 pipeline.

Takes two lists of ScoredProblem — one from Trends, one from Reddit — tags
each entry with a `sources` field, uses a single Gemini call to identify
semantically duplicate problems, collapses duplicates (higher score wins;
ties go to the Trends entry), and returns the combined list sorted by
opportunity_score descending.

Contract:
  - Inputs: two pre-filtered (opportunity_score >= 4.5) lists.
  - Output: single sorted list with `sources` populated, duplicates collapsed.
  - Guarantee: never raises. On AI/parse failure, returns a plain tagged union.

`sources` is added here (not in the scorer) because it is a cross-source
concept — the scorer processes each source independently and has no view of
both at once. Entries are tagged by building shallow copies so the caller's
original lists are not mutated.
"""
import json
from typing import TYPE_CHECKING

from app.clients.gemini import client as _client

if TYPE_CHECKING:
    from app.pipeline.scorer import ScoredProblem


MODEL_NAME = "gemini-2.5-flash-lite"


def _build_dedup_prompt(
    trends: list["ScoredProblem"],
    reddit: list["ScoredProblem"],
) -> str:
    """Build a focused prompt asking the model to identify duplicate problem pairs."""
    trends_lines = "\n".join(
        f"{i + 1}. {p['problem_name']}: {p['description']}"
        for i, p in enumerate(trends)
    )
    reddit_lines = "\n".join(
        f"{i + 1}. {p['problem_name']}: {p['description']}"
        for i, p in enumerate(reddit)
    )
    return f"""You are comparing two lists of business problems to find duplicates.

Identify pairs where a Trends problem and a Reddit problem describe the SAME underlying pain — not merely related topics, but the same specific struggle that people are actively trying to solve.

Be conservative: only flag pairs that are clearly the same problem. Different facets of a broad topic are NOT duplicates.

Trends problems:
{trends_lines}

Reddit problems:
{reddit_lines}

Return ONLY a JSON array of {{"trends_index": int, "reddit_index": int}} pairs (1-indexed).
Return [] if no clear duplicates exist. No markdown fences, no commentary.

Example: [{{"trends_index": 2, "reddit_index": 5}}]"""


def merge_and_dedupe(
    trends_problems: list["ScoredProblem"],
    reddit_problems: list["ScoredProblem"],
) -> list["ScoredProblem"]:
    """
    Merge Trends and Reddit results, collapsing semantic duplicates.

    Every entry in the returned list has a `sources` field:
      - ["trends"]           — came from Trends only
      - ["reddit"]           — came from Reddit only
      - ["trends", "reddit"] — appeared in both; higher-scored version kept

    Args:
        trends_problems: Scored, filtered problems from the Trends chain.
        reddit_problems: Scored, filtered problems from the Reddit chain.

    Returns:
        Combined list sorted by opportunity_score descending. Never raises.
    """
    # Build tagged copies — do not mutate the caller's lists.
    trends = [{**p, "sources": ["trends"]} for p in trends_problems]
    reddit = [{**p, "sources": ["reddit"]} for p in reddit_problems]

    if not trends and not reddit:
        return []
    if not trends:
        return sorted(reddit, key=lambda p: p["opportunity_score"], reverse=True)
    if not reddit:
        return sorted(trends, key=lambda p: p["opportunity_score"], reverse=True)

    try:
        # ── AI dedup call ─────────────────────────────────────────────────────
        prompt = _build_dedup_prompt(trends, reddit)
        response = _client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )
        raw = (response.text or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        pairs = json.loads(raw)
        if not isinstance(pairs, list):
            raise ValueError(f"Expected list from model, got {type(pairs).__name__}")

        # ── Apply dedup pairs ─────────────────────────────────────────────────
        trends_dropped: set[int] = set()  # 0-based indices to remove from trends
        reddit_dropped: set[int] = set()  # 0-based indices to remove from reddit
        # Track which indices have already been used so one entry can't be
        # collapsed twice if the model returns overlapping pairs.
        trends_used: set[int] = set()
        reddit_used: set[int] = set()

        for pair in pairs:
            ti = int(pair["trends_index"]) - 1  # convert to 0-based
            ri = int(pair["reddit_index"]) - 1

            if ti < 0 or ti >= len(trends) or ri < 0 or ri >= len(reddit):
                print(f"  ⚠️  Merger: pair ({ti+1}, {ri+1}) out of bounds — skipping")
                continue

            if ti in trends_used or ri in reddit_used:
                continue  # already part of another collapsed pair

            t_entry = trends[ti]
            r_entry = reddit[ri]

            # Higher score wins; ties go to the Trends entry.
            if r_entry["opportunity_score"] > t_entry["opportunity_score"]:
                survivor = r_entry
                trends_dropped.add(ti)
                other = t_entry
            else:
                survivor = t_entry
                reddit_dropped.add(ri)
                other = r_entry

            survivor["sources"] = ["trends", "reddit"]
            # Union countries preserving insertion order
            for country in other["countries"]:
                if country not in survivor["countries"]:
                    survivor["countries"].append(country)

            trends_used.add(ti)
            reddit_used.add(ri)

        # ── Assemble survivors ────────────────────────────────────────────────
        surviving = (
            [p for i, p in enumerate(trends) if i not in trends_dropped]
            + [p for i, p in enumerate(reddit) if i not in reddit_dropped]
        )
        result = sorted(surviving, key=lambda p: p["opportunity_score"], reverse=True)

        dual_count = sum(1 for p in result if len(p.get("sources", [])) == 2)
        print(
            f"Merger: {len(result)} unique problem(s) "
            f"({dual_count} duplicate pair(s) collapsed across sources)."
        )
        return result

    except Exception as e:
        print(f"⚠️  Merger AI call failed ({type(e).__name__}: {e}) — returning plain union.")
        fallback = sorted(
            trends + reddit,
            key=lambda p: p["opportunity_score"],
            reverse=True,
        )
        return fallback
