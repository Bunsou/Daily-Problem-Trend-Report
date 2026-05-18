# Task 08 — Documentation, env example, and deployment notes

**Status:** Done
**Depends on:** task01 (config field names), task02 (fetcher behavior) — purely doc
**Unblocks:** task09 (verifier may follow the README to set things up)

## Goal

Make it possible for a fresh developer (or future you) to set up Reddit credentials, install dependencies, and deploy v2 to Render without re-reading source code.

## Files to touch

- `README.md` — add Reddit setup section and v2 environment variables.
- `.env.example` (create if missing) — list every required env var with a placeholder.
- *(No code changes in this task — documentation only.)*

## Implementation steps

### 1. README — new "Reddit Setup" subsection

Place under the existing environment / setup section. Use the step-by-step from the parent plan **verbatim** (these are operational steps; do not paraphrase):

```
1. Go to https://www.reddit.com/prefs/apps
2. Click "Create app" at the bottom of the page
3. Choose "script" as the app type
4. Name: "trend-engine-v2" (or anything you want)
5. Set redirect URI to http://localhost:8080 (required but unused for script apps)
6. Click "Create app"
7. The 14-character string under the app name is your REDDIT_CLIENT_ID
8. The "secret" field is your REDDIT_CLIENT_SECRET
9. For REDDIT_USER_AGENT, use the format:
   script:trend-engine-v2:v1.0 (by /u/your_reddit_username)
```

### 2. README — environment variables table / section

Document the three new env vars alongside the existing ones:

| Name | Required? | Default | Description |
|---|---|---|---|
| `REDDIT_CLIENT_ID` | yes | — | 14-char ID from Reddit app dashboard. |
| `REDDIT_CLIENT_SECRET` | yes | — | Secret from Reddit app dashboard. |
| `REDDIT_USER_AGENT` | no | `trend-engine-v2` | Recommended: include your username, e.g., `script:trend-engine-v2:v1.0 (by /u/yourname)`. |

(Match whatever format the existing README uses — the table is illustrative.)

### 3. README — Render deployment note

Add a short callout to the deployment section:

> When deploying to Render, add `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, and (optionally) `REDDIT_USER_AGENT` to the service's environment variables, alongside the existing Gemini / SerpApi / Telegram / database variables.

### 4. README — v2 output format description

Update the "Sample output" or "What you'll see" section (whichever exists) so it reflects the new layout: source attribution tag, potential customer line, no solutions block, no buyer-test rationale. A short example block is fine — does not need to be exhaustive.

### 5. `.env.example`

If `.env.example` does not exist, create it. It should list every env var consumed by `app.core.config.Settings`, each with a clearly-fake placeholder value. Sort grouped by service for readability. Example layout:

```
# Gemini
GEMINI_API_KEY=

# SerpApi (Google Trends)
SERPAPI_KEY=

# Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Reddit (v2)
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=trend-engine-v2

# FastAPI trigger
TRIGGER_TOKEN=

# Database
DATABASE_URL=
```

Do NOT include any real credentials. Leave required values blank; show the default only for `REDDIT_USER_AGENT`.

### 6. Cross-reference

Add a one-line pointer in the README near the Reddit setup steps: "See `docs/v2-plan.md` for the design rationale behind the Reddit data source addition."

## Acceptance criteria

- A new contributor can follow the README from scratch and successfully run `python -m app.pipeline.reddit_fetcher` without referencing any other source.
- `.env.example` lists every field present on `Settings` — no missing or extra variables.
- The README's deployment section mentions the three new Reddit env vars by name.

## Out of scope

- Do NOT regenerate the entire README from scratch — extend the existing structure.
- Do NOT modify any Python code in this task.
- Do NOT add CI configuration changes (Render env vars are set in Render's UI, not in repo files).
