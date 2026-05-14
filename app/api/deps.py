"""Reusable FastAPI dependencies."""
from typing import Optional

from fastapi import Header, HTTPException, status

from app.core.config import settings


def verify_token(authorization: Optional[str] = Header(None)) -> None:
    """
    Require `Authorization: Bearer <TRIGGER_TOKEN>` on the request.

    Used to gate any endpoint that triggers a pipeline run so randoms can't
    burn API quota by hitting the URL.
    """
    if authorization != f"Bearer {settings.trigger_token}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )
