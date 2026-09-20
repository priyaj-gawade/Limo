"""Transformation Jobs REST API router with SSE streaming and resource authorization."""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.responses import StreamingResponse

from ...auth.config import auth_config
from ...auth.dependencies import authorize_resource, get_current_user
from ...models.content import CanonicalContent
from ...models.enums import JobState
from ...models.job import TransformationJob
from ...models.user import User
from ...services.job_service import job_service
from ...services.transformation.event_broker import event_broker

logger = logging.getLogger("limo.api.jobs")

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get("", response_model=List[TransformationJob])
async def list_jobs(
    project_id: Optional[str] = Query(None, description="Filter jobs by project"),
    session_id: Optional[str] = Query(None, description="Filter jobs by chat session"),
    state: Optional[JobState] = Query(None, description="Filter jobs by lifecycle state"),
    current_user: User = Depends(get_current_user),
) -> List[TransformationJob]:
    """List transformation jobs with optional filtering, scoped to user on web surface."""
    user_scope = current_user.id if auth_config.is_web_surface else None
    return job_service.list_jobs(
        project_id=project_id,
        session_id=session_id,
        state=state,
        user_id=user_scope,
    )


@router.get("/{job_id}", response_model=TransformationJob)
async def get_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> TransformationJob:
    """Retrieve job execution status, progress, stage, and deliverables."""
    job = job_service.get_job(job_id)
    authorize_resource(job.user_id, current_user)
    return job


@router.post("/{job_id}/cancel", response_model=TransformationJob)
async def cancel_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> TransformationJob:
    """Cancel an active or queued transformation job with cooperative worker signaling."""
    job = job_service.get_job(job_id)
    authorize_resource(job.user_id, current_user)
    return job_service.cancel_job(job_id)


@router.get("/{job_id}/stream")
async def stream_job_events(
    job_id: str,
    after_sequence: int = Query(0, ge=0, description="Resume event stream after sequence number"),
    last_event_id: Optional[str] = Header(None, alias="Last-Event-ID"),
    current_user: User = Depends(get_current_user),
):
    """Server-Sent Events (SSE) live progress and deliverable stream with durable replay."""
    job = job_service.get_job(job_id)
    authorize_resource(job.user_id, current_user)

    # Determine sequence starting cursor: Last-Event-ID header takes precedence
    start_seq = after_sequence
    if last_event_id:
        try:
            start_seq = int(last_event_id)
        except ValueError:
            pass

    return StreamingResponse(
        event_broker.stream_job_events(job_id=job_id, after_sequence=start_seq),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{job_id}/canonical/{canonical_id}", response_model=CanonicalContent)
async def get_canonical_content(
    job_id: str,
    canonical_id: str,
    current_user: User = Depends(get_current_user),
) -> CanonicalContent:
    """Retrieve intermediate canonical content synthesized during a job."""
    job = job_service.get_job(job_id)
    authorize_resource(job.user_id, current_user)
    return job_service.get_canonical_content(canonical_id)
