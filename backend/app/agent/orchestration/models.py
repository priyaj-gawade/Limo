"""Typed data models for background workflow states and configurations."""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class WorkflowStage(StrEnum):
    """Stages of document and media generation pipeline."""
    INGEST = "ingest"
    CANONICAL = "canonical"
    GENERATE = "generate"
    VALIDATE = "validate"
    DELIVER = "deliver"


from ...models.enums import WorkflowStatus


class WorkflowConfig(BaseModel):
    """Configuration parameterizing a background generation workflow."""
    job_id: str
    project_id: str
    source_ids: List[str] = Field(default_factory=list)
    requested_formats: List[str] = Field(default_factory=list)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    target_stages: List[WorkflowStage] = Field(default_factory=lambda: [
        WorkflowStage.INGEST,
        WorkflowStage.CANONICAL,
        WorkflowStage.GENERATE,
        WorkflowStage.VALIDATE,
        WorkflowStage.DELIVER,
    ])


class WorkflowState(BaseModel):
    """Runtime snapshot of an orchestrated workflow."""
    job_id: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    current_stage: Optional[WorkflowStage] = None
    completed_stages: List[WorkflowStage] = Field(default_factory=list)
    stage_data: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
