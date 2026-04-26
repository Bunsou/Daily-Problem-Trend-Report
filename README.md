# Trend Engine

A daily cron pipeline that fetches Google Trends, processes them through AI
stages (classify → analyze → score → novelty), and delivers a Telegram briefing.

## Local setup

1. Create and activate a virtualenv: `python -m venv venv && source venv/bin/activate`
2. Install deps: `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and fill in the required keys (see "Environment variables" below).
4. Run the database migration: `alembic upgrade head`
5. Run the pipeline: `python main.py --no-send` (drops the Telegram send so you can iterate)

## Environment variables

All variables are required. The pipeline will fail fast at startup if any are missing.

| Var | Purpose |
| --- | --- |
| `GEMINI_API_KEY` | Google Generative AI API key |
| `SERPAPI_KEY` | SerpApi key for Google Trends fetcher |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Chat ID to deliver briefings to |
| `DATABASE_URL` | Postgres connection string (see "Database setup" below) |

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
2. Create a new Cron Job pointing at `main.py`.
3. Set the build command so migrations run on every deploy:
   ```
   pip install -r requirements.txt && alembic upgrade head
   ```
4. Set the start command:
   ```
   python main.py
   ```
5. Set the schedule (e.g. `0 13 * * *` for 13:00 UTC daily).
6. Add every variable from the "Environment variables" table above as a
   Render environment variable, including `DATABASE_URL`.

## Operations

- Re-run the pipeline manually: `python main.py` (or `--no-send` to skip Telegram, `--fresh` to ignore today's stage cache).
- Re-deliver an already-generated briefing without re-running the pipeline:
  `python deliverer.py --send`.
- Inspect today's stored history: `psql "$DATABASE_URL" -c "SELECT run_date, problem_name, opportunity_score FROM novelty_history WHERE run_date = CURRENT_DATE ORDER BY opportunity_score DESC;"`
