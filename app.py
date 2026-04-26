"""
FastAPI HTTP wrapper for the Daily Problem Trend Report pipeline.

Exposes the pipeline as endpoints for external scheduling (cron-job.org)
and health monitoring (keep-alive pings).
"""
import os
import asyncio
from datetime import datetime
from fastapi import FastAPI, HTTPException, Header
from typing import Optional
# Token-based auth so randoms can't trigger your pipeline
from config import TRIGGER_TOKEN


from main import run_pipeline


app = FastAPI(title="Daily Problem Trend Report API", version="1.0")


@app.get("/health")
def health():
    """Lightweight endpoint for keep-alive pings and uptime checks."""
    return {
        "status": "ok",
        "message": "Daily Problem Trend Report is running",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/run-pipeline")
async def trigger_pipeline(authorization: Optional[str] = Header(None)):
    """
    Trigger a full pipeline run.
    
    Requires `Authorization: Bearer <TRIGGER_TOKEN>` header to prevent
    unauthorized triggering.
    
    Returns immediately with a "started" response — the pipeline runs
    asynchronously in the background. This avoids HTTP timeout issues
    when the pipeline takes longer than 30 seconds.
    """
    if not TRIGGER_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="Server misconfigured: TRIGGER_TOKEN not set",
        )
    
    expected = f"Bearer {TRIGGER_TOKEN}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # Run the pipeline in a background task so HTTP returns quickly.
    # The actual work happens after the response is sent.
    asyncio.create_task(_run_pipeline_async())
    
    return {
        "status": "started",
        "message": "Pipeline running in background. Check Telegram for results.",
        "started_at": datetime.now().isoformat(),
    }


async def _run_pipeline_async():
    """Run the synchronous pipeline in a thread to avoid blocking the event loop."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, run_pipeline, True, False)
    # run_pipeline(send_telegram=True, fresh=False)