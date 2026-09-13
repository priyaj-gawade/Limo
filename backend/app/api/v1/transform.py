"""Transformation REST API router exposing contract-only multi-format pipeline requests."""

from typing import List, Optional
from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field

from ...models.enums import OutputFormat
from ...models.job import GenerationConfig, TransformationJob
from ...services.transform_service import transform_service

router = APIRouter(prefix="/transform", tags=["Transform"])


class TransformRequest(BaseModel):
    """Payload for submitting a multi-deliverable transformation request."""
    requested_formats: List[OutputFormat] = Field(
        min_length=1,
        description="Target output deliverables (strictly OutputFormat enums)"
    )
    source_ids: List[str] = Field(
        default_factory=list,
        description="Explicit list of ingested Source IDs to transform"
    )
    prompt: Optional[str] = Field(
        default=None,
        description="Direct user instructions, prompt, or topic"
    )
    inline_content: Optional[str] = Field(
        default=None,
        description="Raw textual content to ingest into a source and transform"
    )
    configuration: Optional[GenerationConfig] = Field(
        default=None,
        description="Applied generation parameters"
    )
    project_id: Optional[str] = Field(
        default=None,
        description="Associated project ID"
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Triggering chat session ID"
    )


@router.post("", response_model=TransformationJob, status_code=status.HTTP_201_CREATED)
async def create_transform_request(req: TransformRequest) -> TransformationJob:
    """Create a persistent contract for a multi-format transformation request.

    Note: D3 establishes contract persistence only (state: QUEUED).
    Actual autonomous generation and worker execution belong to later phases.
    """
    return transform_service.create_transform_contract(
        requested_formats=req.requested_formats,
        source_ids=req.source_ids,
        prompt=req.prompt,
        inline_content=req.inline_content,
        configuration=req.configuration,
        project_id=req.project_id,
        session_id=req.session_id,
    )


@router.get("", response_model=List[TransformationJob])
async def list_transform_requests(
    project_id: Optional[str] = Query(None, description="Filter transform contracts by project"),
    session_id: Optional[str] = Query(None, description="Filter transform contracts by session"),
) -> List[TransformationJob]:
    """List transformation contracts ordered by creation timestamp."""
    return transform_service.list_transform_contracts(
        project_id=project_id,
        session_id=session_id,
    )


@router.get("/{job_id}", response_model=TransformationJob)
async def get_transform_status(job_id: str) -> TransformationJob:
    """Retrieve transformation execution contract status, progress, and deliverable links."""
    return transform_service.get_transform_contract(job_id)
