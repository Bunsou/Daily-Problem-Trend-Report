# Trend Engine

A daily cron pipeline that fetches Google Trends and Reddit posts, processes
them through AI stages (classify → analyze → score → novelty), merges results
across sources with deduplication, and delivers a Telegram briefing.

See `docs/v2-plan.md` for the design rationale behind the Reddit data source addition.

## Local setup

1. Create and activate a virtualenv: `python -m venv venv && source venv/bin/activate`
2. Install deps: `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and fill in the required keys (see "Environment variables" below).
4. Set up Reddit credentials (see "Reddit setup" below).
5. Run the database migration: `alembic upgrade head`
6. Run the pipeline: `python -m app.pipeline.orchestrator --no-send` (skips Telegram so you can iterate)

## Environment variables

Required variables cause a startup `ValidationError` if missing. Optional ones have defaults.

| Var | Required | Default | Purpose |
| --- | --- | --- | --- |
| `GEMINI_API_KEY` | yes | — | Google Generative AI API key |
| `SERPAPI_KEY` | yes | — | SerpApi key for Google Trends fetcher |
| `TELEGRAM_BOT_TOKEN` | yes | — | Telegram bot token |
| `TELEGRAM_CHAT_ID` | yes | — | Chat ID to deliver briefings to |
| `DATABASE_URL` | yes | — | Postgres connection string (see "Database setup" below) |
| `TRIGGER_TOKEN` | yes | — | Bearer token for the FastAPI `/pipeline/trigger` endpoint |

## Reddit data

This project reads from Reddit's public `.json` endpoints. No API keys or authentication are required. The fetcher identifies itself with a descriptive User-Agent and is rate-limit-aware. See `app/pipeline/reddit_fetcher.py` for details.

## Database setup

Novelty history (the past 7 days of scored problems used to tag today's
problems as new / recurring / returning / evolving) is persisted in Postgres.
Everything else (fetcher cache, pipeline output, stage cache) stays on the
local filesystem.

We use [Neon](https://neon.tech) for hosted Postgres because Render Cron Jobs
have an ephemeral filesystem and need a managed database.

### One-time setup

1. Sign up at [neon.tech](https://neon.tech).
2. Create a new project. Note the connection string Neon shows you — it looks
   like `postgresql://user:password@ep-xxx.region.neon.tech/dbname?sslmode=require`.
3. Convert it to the SQLAlchemy / psycopg2 driver form by inserting `+psycopg2`
   after `postgresql`:
   ```
   postgresql+psycopg2://user:password@ep-xxx.region.neon.tech/dbname?sslmode=require
   ```
4. Add it to your `.env`:
   ```
   DATABASE_URL=postgresql+psycopg2://user:password@ep-xxx.region.neon.tech/dbname?sslmode=require
   ```
5. Create the `novelty_history` table:
   ```
   alembic upgrade head
   ```

### Verifying the schema

```
psql "$DATABASE_URL" -c "\d novelty_history"
```

You should see a table with columns: `id`, `run_date`, `problem_name`,
`description`, `category`, `opportunity_score`, `created_at`, plus an index on
`run_date`.

### Failure behavior

If the database is unreachable at runtime, the pipeline does not crash. It
logs a warning and treats the history as empty (so every problem on that run
will be tagged "new"). This keeps the daily briefing flowing even during a
Neon outage. Once the database is reachable again, normal novelty detection
resumes on the next run.

## Render deployment

This pipeline is designed to run as a [Render Cron Job](https://render.com/docs/cronjobs).

1. Connect your GitHub repo in the Render dashboard.
2. Create a new Cron Job and set the build command so migrations run on every deploy:
   ```
   pip install -r requirements.txt && alembic upgrade head
   ```
3. Set the start command:
   ```
   python -m app.pipeline.orchestrator
   ```
4. Set the schedule (e.g. `0 13 * * *` for 13:00 UTC daily).
5. Add every variable from the "Environment variables" table above as a
   Render environment variable, including `DATABASE_URL`.

## Operations

- Re-run the pipeline: `python -m app.pipeline.orchestrator` (add `--no-send` to skip Telegram, `--fresh` to ignore today's stage cache).
- Re-deliver a cached briefing without re-running the pipeline: `python -m app.pipeline.deliverer --send`.
- Smoke-test the Reddit fetcher in isolation: `python -m app.pipeline.reddit_fetcher`.
- Inspect today's stored history: `psql "$DATABASE_URL" -c "SELECT run_date, problem_name, opportunity_score FROM novelty_history WHERE run_date = CURRENT_DATE ORDER BY opportunity_score DESC;"`

## Sample output (v2 format)

```
📊 Daily Opportunity Radar — May 14, 2026

5 qualifying opportunities today (3 from Trends, 4 from Reddit)
────────────────────────────────────────

1. 🆕 [NEW] Filing flight cancellation claims [from: trends, reddit]
   Category: legal  •  Score: 7.8
   Demand: 8  •  Monetization: 9  •  Buildability: 7

   💡 Proven lead-gen category; differentiation lies in speed of intake.

   🎯 Potential customer: Consumer law firms — they already buy leads via Google Ads.

   📝 Travellers whose flights were cancelled are searching for templates and deadlines to claim EU261 compensation before their window closes.

   📌 Recurring theme — seen 3 times in the past 7 days.
```
