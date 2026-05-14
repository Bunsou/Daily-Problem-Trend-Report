"""
FastAPI entry point for the Daily Problem Trend Report.

Exposes the pipeline as HTTP endpoints for external scheduling
(cron-job.org) and uptime monitoring.

Run with: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import health, pipeline
from app.db.session import dispose_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: nothing to warm — engine is lazy, gemini client is module-scope.
    yield
    # Shutdown: close pooled DB connections cleanly.
    dispose_engine()


app = FastAPI(
    title="Daily Problem Trend Report API",
    version="1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(pipeline.router)
