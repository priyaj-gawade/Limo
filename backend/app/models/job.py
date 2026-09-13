"""TransformationJob and GenerationConfig domain models."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import Field, field_validator
from .base import LimoBaseModel
from .enums import JobState, OutputFormat
from .generation_config import (
    GenerationConfig,
    PresentationOptions,
    VideoOptions,
    DocumentOptions,
    SocialOptions,
    InfographicOptions,
)
from ..core.ids import generate_job_id


class TransformationJob(LimoBaseModel):
    """Execution contract tracking an asynchronous multi-deliverable transformation request."""

    id: str = Field(default_factory=generate_job_id, description="Stable job ID with 'job_' prefix")
    project_id: Optional[str] = Field(default=None, description="Associated project ID")
    session_id: Optional[str] = Field(default=None, description="Triggering chat session ID if initiated from chat")
    prompt: Optional[str] = Field(default=None, description="Explicit user instruction, prompt, or topic")
    source_ids: List[str] = Field(default_factory=list, description="Explicit list of ingested Source IDs to transform")
    requested_formats: List[OutputFormat] = Field(
        min_length=1,
        description="List of target transformation deliverables (strictly OutputFormat enums)"
    )
    configuration: GenerationConfig = Field(
        default_factory=GenerationConfig,
        description="Applied generation parameters"
    )

    state: JobState = Field(default=JobState.QUEUED, description="Current lifecycle state of the background job")
    progress: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Overall execution progress from 0.0 (started) to 1.0 (completed)"
    )
    current_stage: Optional[str] = Field(
        default=None,
        description="Human-readable execution stage indicator (e.g. 'Synthesizing Canonical Content')"
    )
    error: Optional[str] = Field(default=None, description="Diagnostic error message if state is FAILED")
    artifact_ids: List[str] = Field(
        default_factory=list,
        description="IDs of deliverables successfully generated and registered by this job"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC job enqueue timestamp"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC last status update timestamp"
    )

    @field_validator("id")
    @classmethod
    def validate_job_id(cls, v: str) -> str:
        if not v.startswith("job_"):
            raise ValueError("TransformationJob ID must start with 'job_'")
        return v
