"""Pydantic response models for the HTTP API."""
from datetime import datetime

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    message: str
    timestamp: datetime


class PipelineStartedResponse(BaseModel):
    status: str
    message: str
    started_at: datetime
