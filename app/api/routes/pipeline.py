"""Pipeline trigger endpoint."""
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends

from app.api.deps import verify_token
from app.pipeline.orchestrator import run_pipeline
from app.schemas.responses import PipelineStartedResponse


router = APIRouter(tags=["pipeline"])


@router.post(
    "/run-pipeline",
    response_model=PipelineStartedResponse,
    dependencies=[Depends(verify_token)],
)
def trigger_pipeline(tasks: BackgroundTasks) -> PipelineStartedResponse:
    """
    Trigger a full pipeline run.

    Requires `Authorization: Bearer <TRIGGER_TOKEN>` header.

    Returns immediately with a "started" response — the pipeline runs
    as a FastAPI BackgroundTask after the HTTP response is sent so the
    cron-job.org request doesn't time out on long runs.
    """
    tasks.add_task(run_pipeline, send_telegram=True, fresh=False)
    return PipelineStartedResponse(
        status="started",
        message="Pipeline running in background. Check Telegram for results.",
        started_at=datetime.now(),
    )
