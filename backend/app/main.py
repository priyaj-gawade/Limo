"""Main FastAPI application entry point for Limo Backend."""

from contextlib import asynccontextmanager
import logging
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError

from .config import settings
from .logging import setup_logging
from .db import init_db
from .storage import storage_service
from .core.middleware import RequestDiagnosticsMiddleware
from .exceptions import (
    LimoException,
    generic_exception_handler,
    limo_exception_handler,
    validation_exception_handler,
)
from .api.v1.router import api_v1_router

logger = logging.getLogger("limo.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup and shutdown hooks."""
    setup_logging()
    logger.info("Initializing %s v%s (environment: %s)", settings.app_name, settings.app_version, settings.environment)

    # Initialize sandboxed filesystem boundaries and SQLite database
    storage_service.ensure_directories()
    init_db()

    # Reconcile stale/abandoned jobs from previous runs and start background workers
    from .services.job_queue import job_queue_manager
    job_queue_manager.reconcile_on_startup()
    job_queue_manager.start_workers()

    yield
    logger.info("Shutting down %s", settings.app_name)
    await job_queue_manager.stop_workers()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
    )

    # Request correlation and diagnostics middleware
    app.add_middleware(RequestDiagnosticsMiddleware)

    # Configure CORS for local desktop & Electron clients
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*", "X-Request-ID"],
    )

    # Register centralized exception handlers
    app.add_exception_handler(LimoException, limo_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)

    # Mount API routers
    app.include_router(api_v1_router, prefix="/api")

    @app.get("/")
    @app.head("/")
    async def root():
        """Root probe confirming backend is operational."""
        return {
            "status": "healthy",
            "app": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs" if settings.is_development else None,
        }

    return app


app = create_app()
