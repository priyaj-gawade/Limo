"""Health check endpoint."""

from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field
from ...config import settings

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    """Health check response payload.

    Notice: Internal deployment/infrastructure environment details are intentionally
    omitted in production to prevent unnecessary environment disclosure.
    """
    status: str = Field(default="healthy", description="Operational status of backend service")
    app: str = Field(description="Application title")
    version: str = Field(description="Semantic version")
    timestamp: str = Field(description="Current server UTC timestamp")
    environment: Optional[str] = Field(
        default=None,
        description="Environment name (only exposed in development/debug modes)"
    )


@router.get("/health", response_model=HealthResponse, response_model_exclude_none=True)
async def check_health() -> HealthResponse:
    """Check backend operational health status."""
    return HealthResponse(
        status="healthy",
        app=settings.app_name,
        version=settings.app_version,
        timestamp=datetime.now(timezone.utc).isoformat(),
        environment=settings.environment if settings.is_development else None
    )
