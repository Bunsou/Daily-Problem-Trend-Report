# Task 05 — Implement the cross-source merger

**Status:** Done
**Depends on:** task04 (scorer's `ScoredProblem` shape is finalized)
**Unblocks:** task06 (orchestrator wires it in)

## Goal

Add a new module that takes two lists of `ScoredProblem` (one from Trends, one from Reddit) and returns a single merged list, with semantically duplicate problems collapsed and a `sources` field on every entry recording where each survived from.

## Files to touch

- **New:** `app/pipeline/merger.py`

## Implementation steps

### 1. Tag entries with `sources` at function entry

`ScoredProblem` does not yet carry a `sources` key. Inside `merge_and_dedupe`, before doing anything else:

- For each entry in `trends_problems`: set `entry["sources"] = ["trends"]`.
- For each entry in `reddit_problems`: set `entry["sources"] = ["reddit"]`.

Do this by mutation OR by building new dicts — either is fine. Document the choice in the module docstring.

`sources` is added at the merger level rather than the scorer level because it is a *cross-source* concept; the scorer has no view of the other source.

### 2. Function signature

```python
def merge_and_dedupe(
    trends_problems: list[ScoredProblem],
    reddit_problems: list[ScoredProblem],
) -> list[ScoredProblem]:
    ...
```

### 3. Dedup AI call

- Use the shared Gemini client (`from app.clients.gemini import client as _client`) — matches `analyzer.py` and `scorer.py`.
- Prompt design (keep it tight and focused):
  - Show two numbered lists: "Trends problems" and "Reddit problems". Each entry shows `problem_name` and `description` only — no need to ship full payloads.
  - Ask: "Identify pairs that describe the same underlying pain. Return a JSON array of `{trends_index, reddit_index}` pairs, 1-indexed. Return `[]` if no duplicates."
- Parse the JSON with the same `json.loads` + `try/except` style used in `analyzer.py` and `scorer.py`.

### 4. Apply the dedup pairs

For each `{trends_index, reddit_index}` pair returned by the AI:

- Look up `trends_problems[trends_index - 1]` and `reddit_problems[reddit_index - 1]`.
- Choose the survivor: whichever entry has the higher `opportunity_score`. Ties: keep the Trends entry (deterministic tie-break).
- On the survivor:
  - Set `sources = ["trends", "reddit"]` (preserve the canonical order: trends first, reddit second).
  - Union the `countries` lists, preserving order, removing duplicates.
- Mark the loser for removal.

Then return: `survivors_from_trends + survivors_from_reddit` (concatenation), sorted by `opportunity_score` descending. Sorting here makes downstream cap-application easier.

### 5. Failure handling

If **anything** in the AI call fails (network, malformed JSON, indices out of range), recover by returning the **plain concatenation** of both input lists with each entry tagged only with its original single source. Log the failure with `print` — the pipeline must not crash on merger trouble.

This means the function must be wrapped in a top-level `try / except Exception as e`. Inside the except: `print` a clear failure line, then return the un-merged concatenation. The orchestrator depends on this guarantee.

### 6. Module docstring

State the contract in the docstring:
- Inputs: two pre-filtered (`opportunity_score >= 4.5`) lists.
- Output: a single sorted list with `sources` populated and duplicates collapsed.
- Guarantee: never raises; on AI failure, returns simple union.

### 7. Optional dev-mode `__main__`

If you add one, have it load both cached lists (after task06 sets up per-source caching) and print the merged result. This is *optional*; skip if it requires too much scaffolding.

## Acceptance criteria

- `merge_and_dedupe([], [])` returns `[]`.
- `merge_and_dedupe([t1], [])` returns `[t1]` with `t1["sources"] == ["trends"]`.
- `merge_and_dedupe([], [r1])` returns `[r1]` with `r1["sources"] == ["reddit"]`.
- When the AI identifies a pair, the returned list contains one combined entry with `sources == ["trends", "reddit"]` and the higher score wins.
- Returned list is sorted by `opportunity_score` descending.
- Forcibly breaking the Gemini call (e.g., raise inside the prompt builder) results in the function returning the un-merged union — no exception propagates out.

## Out of scope

- Do NOT apply caps inside the merger — `apply_caps` lives in the orchestrator (task06).
- Do NOT modify `ScoredProblem` to add `sources` as a required key — it is added dynamically here. (You may extend the TypedDict with `sources: NotRequired[list[str]]` if you want type-checker friendliness, but it is optional.)
- Do NOT introduce embeddings, vector DBs, or similarity heuristics — a single Gemini call is the chosen approach.
