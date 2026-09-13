"""Transformation Jobs REST API router."""

from typing import List, Optional
from fastapi import APIRouter, Query

from ...models.content import CanonicalContent
from ...models.enums import JobState
from ...models.job import TransformationJob
from ...services.job_service import job_service

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get("", response_model=List[TransformationJob])
async def list_jobs(
    project_id: Optional[str] = Query(None, description="Filter jobs by project"),
    session_id: Optional[str] = Query(None, description="Filter jobs by chat session"),
    state: Optional[JobState] = Query(None, description="Filter jobs by lifecycle state"),
) -> List[TransformationJob]:
    """List transformation jobs with optional filtering, ordered by created_at DESC."""
    return job_service.list_jobs(
        project_id=project_id,
        session_id=session_id,
        state=state,
    )


@router.get("/{job_id}", response_model=TransformationJob)
async def get_job(job_id: str) -> TransformationJob:
    """Retrieve job execution status, progress, stage, and deliverables."""
    return job_service.get_job(job_id)


@router.post("/{job_id}/cancel", response_model=TransformationJob)
async def cancel_job(job_id: str) -> TransformationJob:
    """Cancel an active or queued transformation job."""
    return job_service.cancel_job(job_id)


@router.get("/{job_id}/canonical/{canonical_id}", response_model=CanonicalContent)
async def get_canonical_content(job_id: str, canonical_id: str) -> CanonicalContent:
    """Retrieve intermediate canonical content synthesized during a job."""
    # Ensure the job exists first
    job_service.get_job(job_id)
    return job_service.get_canonical_content(canonical_id)
