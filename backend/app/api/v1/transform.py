"""Transformation REST API router exposing contract-only multi-format pipeline requests."""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from ...auth.config import auth_config
from ...auth.dependencies import authorize_resource, get_current_user
from ...models.enums import OutputFormat
from ...models.job import GenerationConfig, TransformationJob
from ...models.user import User
from ...services.chat_service import chat_service
from ...services.project_service import project_service
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
async def create_transform_request(
    req: TransformRequest,
    current_user: User = Depends(get_current_user),
) -> TransformationJob:
    """Create a persistent contract for a multi-format transformation request and enqueue execution."""
    if req.project_id:
        proj = project_service.get_project(req.project_id)
        authorize_resource(proj.user_id, current_user)

    if req.session_id:
        chat = chat_service.get_session(req.session_id)
        owner_id = chat.metadata.get("user_id") if isinstance(chat.metadata, dict) else None
        if not owner_id and chat.project_id:
            try:
                proj = project_service.get_project(chat.project_id)
                owner_id = proj.user_id
            except Exception:
                pass
        authorize_resource(owner_id, current_user)

    return transform_service.create_transform_contract(
        requested_formats=req.requested_formats,
        source_ids=req.source_ids,
        prompt=req.prompt,
        inline_content=req.inline_content,
        configuration=req.configuration,
        project_id=req.project_id,
        session_id=req.session_id,
        user_id=current_user.id if current_user else None,
    )


@router.get("", response_model=List[TransformationJob])
async def list_transform_requests(
    project_id: Optional[str] = Query(None, description="Filter transform contracts by project"),
    session_id: Optional[str] = Query(None, description="Filter transform contracts by session"),
    current_user: User = Depends(get_current_user),
) -> List[TransformationJob]:
    """List transformation contracts ordered by creation timestamp."""
    contracts = transform_service.list_transform_contracts(
        project_id=project_id,
        session_id=session_id,
    )
    if auth_config.is_web_surface:
        contracts = [c for c in contracts if c.user_id == current_user.id or not c.user_id]
    return contracts


@router.get("/{job_id}", response_model=TransformationJob)
async def get_transform_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> TransformationJob:
    """Retrieve transformation execution contract status, progress, and deliverable links."""
    job = transform_service.get_transform_contract(job_id)
    authorize_resource(job.user_id, current_user)
    return job
