# v2 Verification Log

**Date:** 2026-05-14
**Environment:** local (macOS)
**Reddit credentials in .env:** ❌ not yet set — see README "Reddit setup" for steps

---

## Check 1 — End-to-end runs without crashing

**Status:** ⏳ Partially verified — blocked by two independent issues

**What ran:**
- Trends chain executed successfully through all stages: fetch (764 raw) → category_filter (332) → classifier (160) → analyzer (9 problems). All stages cached correctly.
- Reddit chain executed with dummy credentials: every subreddit logged a `401 HTTP response` per-subreddit, returned 0 posts, no crash. The "both sources empty → exit 1" path fired correctly.

**Blockers:**
1. **Transient Gemini 503** — `gemini-2.5-flash` (scorer model) returned `503 UNAVAILABLE` on both attempts. This is Google-side load; retry when demand eases.
2. **Missing Reddit credentials** — `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` not in `.env`. Add real values and re-run.

**Observation — scorer swallows exceptions:**
`score_problems()` catches all exceptions internally and returns `[]` instead of re-raising. As a result, `cached_stage`'s retry mechanism (which only fires on raised exceptions) never activates for scorer API errors. The scorer caches an empty `[]` from the failed call, and subsequent runs use that poisoned cache entry. Workaround: manually delete `scorer_trends_<date>.json` from `.cache/stages/` and re-run. Pre-existing v1 behavior; not introduced by v2.

**Re-verify when:** real Reddit creds added + Gemini load eases.

---

## Check 2 — Briefing format matches the v2 spec

**Status:** ✅ Verified (automated unit test)

- Every entry title contains `[from: <sources>]`.
- Dual-source entries show `[from: trends, reddit]`.
- `🎯 Potential customer:` line present.
- `🎯 Buyer:` line absent.
- `🛠 Solutions:` block absent.
- Header reads `N qualifying opportunities today (X from Trends, Y from Reddit)`.
- Dual-source entries contribute to both X and Y counts (tag-count, not entry-count).
- Missing `sources` key (legacy cache) falls back to `[from: unknown]` without crashing.

---

## Check 3 — Trends-side legal/medical exclusion

**Status:** ✅ Verified (prompt inspection + unit test)

`TRENDS_SOURCE_GUIDANCE` contains the hardcoded exclusion for all six terms: `legal`, `law`, `medical`, `hospital`, `pharmaceutical`, `medicine`. The instruction reads:

> "Additionally, exclude any problems in these domains: legal, law, medical, hospital, pharmaceutical, medicine. Do not extract problems from trends in these categories even if they appear to be real problems."

This section is appended only when `source == "trends"`. It is not present in `REDDIT_SOURCE_GUIDANCE`.

**Live verification:** inspect `analyzer_trends_<date>.json` in `.cache/stages/` after a successful run — no extracted problem should have `category` of legal/medical.

---

## Check 4 — Reddit-side legal/medical topics allowed

**Status:** ✅ Verified (prompt inspection + unit test)

`REDDIT_SOURCE_GUIDANCE` contains no exclusion clause. The word "exclude" does not appear in the Reddit guidance. Reddit posts on legal/medical topics are passed to the analyzer and scored on their merit.

Note: the default subreddit list (`DEFAULT_SUBREDDITS`) does not include legal subreddits (`legaladvice` etc.), so legal posts are unlikely in practice — but the pipeline does not filter them.

---

## Check 5 — Cap behavior

**Status:** ✅ Verified (automated unit test)

`apply_caps(merged, max_trends=4, max_reddit=6)`:
- With 7 Trends and 8 Reddit entries: capped to exactly 4 Trends and 6 Reddit.
- Dual-source entries count toward both budgets simultaneously. With 5 dual-source entries: only 4 are kept (trends budget exhausts first at 4, blocking the 5th even though reddit budget has headroom).
- Output preserves score ordering.

---

## Check 6 — Dedup behavior

**Status:** ⏳ Partially verified — live AI dedup deferred

**Static check passed:** Merger fallback path (AI failure → plain tagged union, sorted by score) tested via monkeypatching.

**Live dedup check:** requires a day where both Trends and Reddit surface the same underlying pain. Will observe over the next 2–3 daily runs once Reddit credentials are set.

When it occurs, verify:
- Single entry in briefing for the duplicate problem.
- Tagged `[from: trends, reddit]`.
- Score is the max of the two pre-merge scores.

---

## Check 7 — Database / novelty history across both sources

**Status:** ⏳ Deferred — requires 2+ successful consecutive daily runs

Novelty detection uses the past 7 days of `novelty_history` rows regardless of source. Once a full run completes successfully, run again the next day and confirm recurring problems are tagged `📅` (returning) or `📈` (recurring).

---

## Check 8 — Per-source pipeline cache

**Status:** ✅ Verified (live run)

After the first run, `.cache/stages/` contained all source-scoped files:

```
analyzer_trends_2026-05-14.json
category_filter_trends_2026-05-14.json
classifier_trends_2026-05-14.json
fetch_reddit_2026-05-14.json
fetch_trends_2026-05-14.json
novelty_trends_2026-05-14.json
scorer_trends_2026-05-14.json
```

The second run (without `--fresh`) loaded all cached stages instantly:
```
⚡ Using cached 'fetch_trends' from today
⚡ Using cached 'category_filter_trends' from today
⚡ Using cached 'classifier_trends' from today
⚡ Using cached 'analyzer_trends' from today
⚡ Using cached 'fetch_reddit' from today
```

No key collisions. `_reddit` and `_trends` suffixes are distinct throughout. `clear_todays_cache()` deletes all `*_<date>.json` files, naturally clearing both chains.

---

## Check 9 — Reddit-unavailable graceful degradation

**Status:** ✅ Verified (live run with bad Reddit credentials)

With `REDDIT_CLIENT_ID=dummy REDDIT_CLIENT_SECRET=dummy`:
- Every subreddit fetch logged: `r/<name>: failed (ResponseException: received 401 HTTP response) — skipping`
- `fetch_reddit_posts()` returned 0 entries, no exception raised.
- Orchestrator logged: `⚠️  No Reddit posts fetched. Check REDDIT_* credentials.`
- Reddit chain returned `[]`.
- Pipeline continued (did not crash on Reddit failure).

Note: in this run both sources returned empty (Trends due to scorer 503, Reddit due to bad creds), so exit code was 1. Once Gemini load eases, re-run with bad Reddit creds only — expect exit code 0 with a Trends-only briefing.

---

## Check 10 — Trends-unavailable graceful degradation

**Status:** ⏳ Deferred — requires real Reddit credentials first

To test: temporarily set `SERPAPI_KEY=bad_key` in `.env`, run `--fresh`. Expect:
- Trends fetch logs a SerpApi error and returns 0 entries.
- Trends chain returns `[]`.
- Reddit chain runs normally and produces a Reddit-only briefing.
- Exit code 0.

Restore `SERPAPI_KEY` after verifying.

---

## Summary

| Check | Status | Notes |
|---|---|---|
| 1. End-to-end no crash | ⏳ | Blocked: Gemini 503 + missing Reddit creds |
| 2. Briefing format | ✅ | All format assertions pass |
| 3. Trends legal exclusion | ✅ | Hardcoded exclusion confirmed in prompt |
| 4. Reddit legal allowed | ✅ | No exclusion clause in Reddit guidance |
| 5. Cap behavior | ✅ | 4 Trends / 6 Reddit caps enforced |
| 6. Dedup behavior | ⏳ | Fallback tested; live AI dedup deferred |
| 7. Novelty across sources | ⏳ | Requires 2+ days of successful runs |
| 8. Per-source cache | ✅ | Source-scoped keys, no collisions, resume works |
| 9. Reddit degradation | ✅ | Per-subreddit isolation, no crash on 401 |
| 10. Trends degradation | ⏳ | Deferred — needs real Reddit creds first |

**4 checks fully verified. 2 checks verified on static/unit path with live portion deferred. 4 checks pending real Reddit credentials + a successful Gemini run.**

## Next steps

1. Add `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, (optionally) `REDDIT_USER_AGENT` to `.env` following the README "Reddit setup" steps.
2. Re-run `python -m app.pipeline.orchestrator --no-send --fresh` when Gemini load has eased.
3. Re-verify checks 1, 9, 10 once both sources run cleanly.
4. After 2 consecutive daily runs, verify check 7 (novelty tracking).
5. Monitor output over 2–3 days to catch check 6 (live dedup) when topic overlap occurs.
