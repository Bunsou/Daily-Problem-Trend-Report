# Task 01 — Add Reddit configuration and dependencies

**Status:** Not started
**Depends on:** none
**Unblocks:** task02, task03, task08

## Goal

Get Reddit credentials and the PRAW dependency wired through `app.core.config.settings` so that downstream modules can rely on validated, typed settings instead of raw `os.getenv`.

## Files to touch

- `app/core/config.py` — extend the `Settings` class.
- `requirements.txt` — add the PRAW pin.

## Implementation steps

### 1. Add three fields to `app.core.config.Settings`

The class currently inherits `BaseSettings`. Add (in lowercase to match the existing convention — Pydantic maps them to `REDDIT_*` env vars):

```python
reddit_client_id: str
reddit_client_secret: str
reddit_user_agent: str = "trend-engine-v2"
```

- `reddit_client_id` and `reddit_client_secret` are **required** — leave them without defaults so a missing value raises a `ValidationError` at import time, matching how `gemini_api_key` etc. behave today.
- `reddit_user_agent` is **optional** with the default literal `"trend-engine-v2"`.

Do NOT add manual `os.getenv` calls or a "validation block." Pydantic `BaseSettings` already provides startup-time validation — that's why this file uses it.

### 2. Add PRAW to `requirements.txt`

Append the line:

```
praw>=7.7,<8.0
```

Keep the existing pin style (no version unification work). Do not reorder or rewrite the file.

## Acceptance criteria

- Importing `from app.core.config import settings` with `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` unset raises a clear `pydantic.ValidationError` naming both missing fields.
- With those two env vars set and `REDDIT_USER_AGENT` unset, `settings.reddit_user_agent == "trend-engine-v2"`.
- `pip install -r requirements.txt` resolves and installs PRAW in the 7.7.x line.
- No other files are modified.

## Out of scope

- Do NOT write the README / `.env.example` updates here — those belong to task08.
- Do NOT create the PRAW client wrapper here — that belongs to task02.
- Do NOT touch any pipeline module — config is the only surface this task changes.
