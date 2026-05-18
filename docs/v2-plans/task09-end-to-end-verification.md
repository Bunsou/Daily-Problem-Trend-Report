# Task 09 — End-to-end verification

**Status:** In progress — see verification-log.md
**Depends on:** task01 through task08
**Unblocks:** v2 ship

## Goal

Walk through the 10 verification steps from the parent plan (`docs/v2-plan.md`) and produce a short written confirmation that each behavior holds in the live system. This is the last gate before v2 is considered ready to run daily.

## How to run

For each check below: run the command (or set up the precondition), inspect the output, and record the result in a verification log (a new file `docs/v2-plans/verification-log.md` is fine — or check items off in this file via PR comments).

For checks that require external state (e.g., a day with overlapping topics across Trends and Reddit), note "deferred — will re-check on a day when this surfaces" and move on. Do NOT fake the conditions.

## Checks

### 1. End-to-end runs without crashing

```
python -m app.pipeline.orchestrator --no-send --fresh
```

Both chains fetch, classify, analyze, score, novelty-check, merge, dedupe, cap, and deliver to stdout. Exit code 0. No tracebacks.

### 2. Briefing format matches the new spec

Inspect the printed briefing:
- Each entry shows `[from: ...]` after the problem name.
- `🎯 Potential customer:` line present.
- NO `🎯 Buyer:` line.
- NO `🛠 Solutions:` block.
- Header reads `N qualifying opportunities today (X from Trends, Y from Reddit)`.

### 3. Trends-side legal/medical exclusion

In the rendered briefing, no entry tagged `[from: trends]` (alone) belongs to legal / medical / hospital / pharmaceutical / medicine.

To stress-test: check the analyzer's intermediate cache for the Trends chain (`analyzer_trends.json`) — none of the extracted problems should be in those domains.

### 4. Reddit-side legal/medical allowed

If a r/legaladvice-style post produces a real problem, it MAY appear in the briefing tagged `[from: reddit]`. (Subreddit list in task02 does not include legal subs by default, so this check is mostly hypothetical — confirm by inspection of the Reddit analyzer prompt that no exclusion list is appended for `source == "reddit"`.)

### 5. Cap behavior

- Force a run where Reddit produces 8 qualifying problems. Confirm the briefing shows at most 6 Reddit-only entries (more is allowed only via dual-source dedup credit).
- Same for Trends side with cap = 4.

If a natural run does not exceed the caps, write a small test fixture or manipulate a cached scorer output to simulate it.

### 6. Dedup behavior

Look for a day where both sources surface semantically overlapping problems. When found:
- Verify exactly one entry remains in the briefing for that problem.
- Verify it is tagged `[from: trends, reddit]`.
- Verify its score is the **max** of the two pre-merge scores.

If no overlap occurs on the first verification day, mark as "pending observation" — do not block ship on it, but check the next 2–3 days of output.

### 7. Database / history works across both sources

Run on day 1, then again on day 2. On day 2, problems that recurred should be tagged `📅` (returning) or `📈` (recurring) per `NOVELTY_ICONS`. Inspect a few `novelty_note` strings to confirm they reference past observations correctly. This works regardless of which source surfaced the problem.

### 8. Pipeline cache works per source

```
python -m app.pipeline.orchestrator --no-send
python -m app.pipeline.orchestrator --no-send
```

The second run should reuse cached stages (no Gemini calls for classifier / analyzer / scorer of either source). Inspect cache directory contents — both `*_trends.json` and `*_reddit.json` files exist for every stage.

### 9. Reddit-unavailable graceful degradation

Temporarily corrupt `REDDIT_CLIENT_SECRET` in `.env`, then `--fresh` run. The Trends chain still completes; the Reddit chain logs a clear failure; the briefing renders with only Trends entries (no `[from: reddit]` tags); exit code 0.

Restore credentials afterward.

### 10. Trends-unavailable graceful degradation

Same as #9 but corrupt `SERPAPI_KEY`. Reddit-only briefing should render; exit code 0.

Restore credentials afterward.

## Reporting

Produce a verification log (markdown, in this directory) with one line per check: `✅` / `❌` / `⏳ pending observation`. If any `❌`, file a follow-up task referencing the parent plan section that was violated — do NOT silently patch.

## Out of scope

- Do NOT use this task to add new features. If a verification check fails, fix the underlying task's deliverable; this task is purely a gate.
- Do NOT modify production code as part of running checks. If a check forces you to modify code (e.g., simulating overflow), revert before final sign-off.
