"""API v1 router aggregator."""

from fastapi import APIRouter
from .health import router as health_router
from .projects import router as projects_router
from .sources import router as sources_router
from .chats import router as chats_router
from .jobs import router as jobs_router
from .artifacts import router as artifacts_router
from .transform import router as transform_router
from .voices import router as voices_router

api_v1_router = APIRouter(prefix="/v1")
api_v1_router.include_router(health_router)
api_v1_router.include_router(projects_router)
api_v1_router.include_router(sources_router)
api_v1_router.include_router(chats_router)
api_v1_router.include_router(jobs_router)
api_v1_router.include_router(artifacts_router)
api_v1_router.include_router(transform_router)
api_v1_router.include_router(voices_router)


