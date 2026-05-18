# Task 07 — Update the deliverer briefing format

**Status:** Done
**Depends on:** task04 (`potential_customer`), task05 (`sources` field), task06 (`apply_caps` produces the final list)
**Unblocks:** task09 (verification)

## Goal

Update `app/pipeline/deliverer.py` so the briefing reflects v2's design: no solutions, no buyer_test rationale, a new `potential_customer` line, and a `[from: SOURCES]` attribution tag on every entry. Header counts per source.

## Files to touch

- `app/pipeline/deliverer.py` — modify `format_briefing` and `_format_single_problem`.

## Implementation steps

### 1. Per-problem layout

Replace the current `_format_single_problem` output with:

```
{rank}. {icon} [{NOVELTY_LABEL}] {problem_name} [from: {sources_csv}]
   Category: {category}  •  Score: {opportunity_score}
   Demand: {demand}  •  Monetization: {monetization}  •  Buildability: {buildability}

   💡 {key_insight}

   🎯 Potential customer: {potential_customer}

   📝 {description}

   📌 {novelty_note}   (only if novelty_note is non-empty)
```

Specifically:

- **Add** `[from: <sources>]` at the end of the title line. `sources_csv` is `", ".join(p["sources"])` — typically `trends`, `reddit`, or `trends, reddit`.
- **Add** `🎯 Potential customer: {potential_customer}` line.
- **Remove** the existing `🎯 Buyer: {buyer_test}` line entirely.
- **Remove** the `🛠 Solutions:` header and all the bullet-list lines beneath it.
- Keep the novelty `📌` line only when `novelty_note` is truthy (matches current behavior).
- Use `•` as the visual separator between numeric scores (current code uses `•` already on the demand/monetization/buildability line; keep that. Update the category/score line from `|` to `•` for consistency — see the parent plan's spec).

### 2. Briefing header

Current header:
```
📊 Daily Opportunity Radar — Apr 26, 2026

X qualifying opportunit{y/ies} today
```

New header:
```
📊 Daily Opportunity Radar — Apr 26, 2026

{total} qualifying opportunit{y/ies} today ({n_trends} from Trends, {n_reddit} from Reddit)
```

Where:

- `total = len(problems)`
- `n_trends = sum(1 for p in problems if "trends" in p["sources"])`
- `n_reddit = sum(1 for p in problems if "reddit" in p["sources"])`

Per the parent plan's "Required behavior" section, **the per-source counts are tag-counts**, not entry-counts. A dual-source entry contributes to both `n_trends` and `n_reddit`. This is the same accounting the cap logic uses.

### 3. Defensive read of `sources`

In case `merge_and_dedupe` was bypassed (e.g., when delivering from a v1-era cache file during the transition), default `sources` to `["unknown"]` if missing:

```python
sources = p.get("sources") or ["unknown"]
```

This avoids a `KeyError` on legacy cache without inventing fake attribution.

### 4. Empty-briefing path

`_format_empty_briefing` currently prints "No qualifying opportunities today." plus the "quiet day" explainer. Keep this exactly as-is — empty days don't need source attribution because there's nothing to attribute.

### 5. Update the module docstring

Reflect the new fields and removed sections.

## Acceptance criteria

- A briefing rendered against a freshly-merged list shows the `[from: ...]` tag on every entry.
- A dual-source entry shows `[from: trends, reddit]`.
- No `Buyer:` line and no `Solutions:` block appear anywhere in the output.
- Header line correctly reports `(X from Trends, Y from Reddit)`, and the sum of X+Y can exceed the total when dual-source entries are present.
- Running the deliverer in isolation against a cached output (`python -m app.pipeline.deliverer`) produces a printable briefing without crashing, even if a particular entry happens to lack `potential_customer`.

## Out of scope

- Do NOT touch the Telegram client (`app/clients/telegram.py`).
- Do NOT change the dev-mode `__main__` flag handling (`--send`).
- Do NOT change `NOVELTY_ICONS` mapping.
- Do NOT add HTML / Markdown styling — keep plain text (Telegram is plain-text-friendly here).
