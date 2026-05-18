# Task 04 — Add `potential_customer` to the scorer

**Status:** Done
**Depends on:** none (independent of task02/03)
**Unblocks:** task05, task07 (deliverer reads this new field)

## Goal

Add a short, display-friendly `potential_customer` field to scored problems while keeping the existing `buyer_test` mechanism untouched — `buyer_test` continues to enforce scoring rigor; `potential_customer` is what users actually see in the briefing.

## Files to touch

- `app/pipeline/scorer.py` — extend the TypedDict, the prompt, and the result assembly.

## Implementation steps

### 1. Extend `ScoredProblem`

Add the new field to the TypedDict:

```python
class ScoredProblem(Problem):
    buyer_test: str
    potential_customer: str   # NEW — 1-2 sentence display-friendly buyer naming
    demand: int
    monetization: int
    buildability: int
    opportunity_score: float
    key_insight: str
    solutions: list[str]
    novelty: str
    novelty_note: str
```

Keep `buyer_test` and `solutions` exactly as they are — `buyer_test` still drives the monetization penalty; `solutions` continues to be generated even though task07 will stop displaying it (intentional retention — the scorer is the source of rigor, the deliverer is the source of brevity).

### 2. Update the scorer prompt

Inside `build_scorer_prompt`, add a section describing `potential_customer`:

- 1–2 sentences max.
- Names the buyer persona with **just enough** context to make it concrete (industry, size, why-they-care).
- NOT a copy of `buyer_test` — that field already exists and is more verbose.
- Examples to anchor the model:
  - Good: `"Personal injury law firms — they already buy leads via Google Ads."`
  - Good: `"Small business HR managers handling first-time disputes."`
  - Bad: `"Anyone interested in legal services."`
  - Bad: a sentence that just restates the buyer_test rationale.

Add `"potential_customer"` to the output schema description and the example JSON object at the bottom of the prompt.

### 3. Update the JSON output parsing

In `score_problems`, when assembling each `ScoredProblem`, pull `potential_customer` from `score_data` with a safe default:

```python
"potential_customer": score_data.get("potential_customer", ""),
```

Place it next to the `buyer_test` line so the diff is easy to review.

### 4. Keep the geometric-mean math and `MIN_OPPORTUNITY_SCORE` threshold unchanged

This task is purely additive on the output side.

## Acceptance criteria

- Re-running the scorer dev mode (`python -m app.pipeline.scorer`) on a cached analyzer output produces objects with a non-empty `potential_customer` for the majority of scored problems.
- An entry where the buyer test fails (`monetization` 1–3) has a `potential_customer` that either matches the failure (e.g., "No clear buyer — see buyer_test") or is empty. Either is acceptable; the goal is no crash.
- `ScoredProblem` typing reflects the new field; static type-checkers do not complain at the deliverer's eventual access.
- Existing fields (`buyer_test`, `solutions`, etc.) remain in the output payload unchanged.

## Out of scope

- Do NOT remove `solutions` from the scorer prompt or TypedDict — the deliverer task (task07) will simply stop rendering them. Generating them keeps the scoring exercise honest.
- Do NOT change the threshold (`MIN_OPPORTUNITY_SCORE = 4.5`). The plan applies that same threshold per-source, before merge — orchestrator-side concern.
- Do NOT touch the deliverer in this task.
