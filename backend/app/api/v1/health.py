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


@router.get("/health/db")
async def check_db_health():
    """Verify live database connectivity, dialect engine, and keepalive status."""
    import time
    from ...db.connection import get_connection
    from ...services.keepalive import keepalive_worker
    from ...storage.web_storage import WebArtifactStorage

    t0 = time.perf_counter()
    db_status = "error"
    db_engine = "unknown"
    db_name = None
    server_time = None
    error_msg = None

    try:
        with get_connection() as conn:
            db_engine = "postgres" if getattr(conn, "is_postgres", False) else "sqlite"
            if getattr(conn, "is_postgres", False):
                row = conn.execute("SELECT current_database() AS db_name, NOW() AS s_time;").fetchone()
                db_name = row["db_name"] if row else None
                server_time = str(row["s_time"]) if row and "s_time" in row else None
            else:
                row = conn.execute("SELECT datetime('now') AS s_time;").fetchone()
                db_name = settings.db_name
                server_time = str(row["s_time"]) if row and "s_time" in row else None
            db_status = "connected"
    except Exception as e:
        error_msg = str(e)

    latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    storage_probe = WebArtifactStorage()

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "database": {
            "status": db_status,
            "engine": db_engine,
            "database_name": db_name,
            "server_time": server_time,
            "latency_ms": latency_ms,
            "error": error_msg,
        },
        "keepalive": keepalive_worker.get_stats(),
        "storage": {
            "engine": "supabase" if storage_probe.is_configured else "local",
            "bucket": storage_probe.bucket,
            "configured": storage_probe.is_configured,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

