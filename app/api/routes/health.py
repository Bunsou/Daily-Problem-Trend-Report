"""Health-check route — used by uptime monitors and keep-alive pings."""
from datetime import datetime

from fastapi import APIRouter

from app.schemas.responses import HealthResponse


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Lightweight endpoint for keep-alive pings and uptime checks."""
    return HealthResponse(
        status="ok",
        message="Daily Problem Trend Report is running",
        timestamp=datetime.now(),
    )
