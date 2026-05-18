# Task 03 — Make the analyzer source-aware

**Status:** Done
**Depends on:** task01 (settings) — but not task02; the analyzer just takes a `source` string.
**Unblocks:** task06 (orchestrator passes `source` per chain)

## Goal

Teach `app/pipeline/analyzer.py` to handle both Google Trends entries and Reddit posts via a single `source` parameter, sharing the core "what counts as a real problem" rules but appending source-specific framing. Hardcode the legal/medical/hospital/pharmaceutical exclusion for Trends only.

## Files to touch

- `app/pipeline/analyzer.py` — refactor `analyze_trends` and `build_prompt`.

## Implementation steps

### 1. New signature

```python
def analyze_trends(entries: list[dict], source: str) -> list[Problem]: ...
```

- `source` must be `"trends"` or `"reddit"`. Raise `ValueError` for anything else — fail loud rather than silently miscategorize.
- Keep `Problem` TypedDict unchanged; the schema is source-agnostic.

### 2. Extract a shared rules constant

Pull the parts of the current prompt that apply to **both** sources into a module-level `SHARED_ANALYZER_RULES` string:

- "What counts as a real problem" — the solution-seeking intent rule.
- "✅ QUALIFIES / ❌ DOES NOT QUALIFY" example block.
- "What this means in practice" (the quality-over-quantity guidance).
- The output JSON schema (`problem_name`, `description`, `evidence`, `category`, `countries`).
- "When to return nothing" rule.

These are the source-agnostic invariants. Do NOT include the Trends-specific examples like "Pfizer stock" in the shared block — those are Trends-flavored. (Optional: keep them; just be intentional about what's shared.)

### 3. Source-specific prompt sections

`build_prompt(entries, source)` should branch:

**When `source == "trends"`** — append:
- "Input is short search query strings with country and category metadata."
- "Infer problems from query phrasing and related searches."
- **Hardcoded exclusion (verbatim wording matters):**

  > Additionally, exclude any problems in these domains: legal, law, medical, hospital, pharmaceutical, medicine. Do not extract problems from trends in these categories even if they appear to be real problems. They are out of scope for this analysis.

**When `source == "reddit"`** — append:
- "Input is Reddit posts with title and body text (long-form descriptions)."
- "Quote directly from post bodies when extracting evidence."
- "Each post's title is generally the problem statement; the body provides context."
- "Treat post engagement (upvotes, comments) as signal strength."
- "Use the subreddit name as a category hint (e.g., posts from r/Accounting are likely finance/accounting domain)."
- **No hardcoded exclusion list** — Reddit is unfiltered.

### 4. Rendering the input block

The current code formats each entry as:
```
- "<query>" (in: <countries>) [<categories>]
  Related searches: <related_queries>
```

For Reddit entries, that format is wrong (no related queries, body text is the real signal). Render Reddit entries with subreddit / upvotes / title / body, e.g.:

```
- r/<subreddit> (▲<search_volume>, 💬<num_comments>): "<query (post title)>"
  Body: <post_body (truncated to a sensible length, e.g., 1500 chars)>
```

Truncate `post_body` to keep the prompt under a reasonable token budget — pick a constant like `MAX_POST_BODY_CHARS = 1500` and slice with an ellipsis.

### 5. Preserve the existing backward-compat shim

The current code post-processes problems to copy `evidence` into `source_trends` for downstream consumers. Keep that — the scorer still reads `source_trends`.

### 6. Update the module docstring + `__main__` block

The `if __name__ == "__main__":` smoke section currently chains `fetch_trends → filter_by_category → classify_trends → analyze_trends`. Update it so `analyze_trends(trends, source="trends")` is called explicitly. (Don't add a Reddit smoke path here — that belongs to a separate dev session.)

## Acceptance criteria

- `analyze_trends(entries, source="trends")` produces the same outputs as the v1 analyzer did for the same inputs (no behavioral drift on the Trends path beyond the hardcoded exclusion).
- `analyze_trends(entries, source="reddit")` produces problems whose `evidence` strings are quotes pulled from post bodies (verify by inspecting a real run's output).
- A Trends entry whose dominant theme is legal/medical/hospital/pharmaceutical/medicine does NOT appear in the analyzer's output. Reddit entries on the same topics DO appear.
- `analyze_trends(entries, source="bogus")` raises `ValueError`.
- The shared rules text is defined exactly once; both paths concatenate it with their suffix.

## Out of scope

- Do NOT change the `Problem` TypedDict.
- Do NOT change `MODEL_NAME`.
- Do NOT add retry / caching here — orchestrator handles that.
- Do NOT add fallback that returns Trends-style problems for Reddit input or vice versa — strict source separation.
