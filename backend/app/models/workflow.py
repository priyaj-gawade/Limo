"""Transformation Workflow domain models (Phase D6.4).

Defines structured task units, workflow execution tracking, and frozen outcome representations:
- TaskStatus: Lifecycle of an individual planned deliverable task.
- DeliverableTask: Work unit tracking native execution or external engine contract holding.
- TransformationWorkflow: State representation of an active or completed transformation DAG.
- TransformationWorkflowResult: Frozen, structured result model handed to D6.5.
"""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Dict, List, Optional
from pydantic import ConfigDict, Field, field_validator

from .artifact import Artifact
from .base import LimoBaseModel
from .enums import OutputFormat, WorkflowStatus
from .transformation import EngineType
from ..core.ids import generate_task_id, generate_workflow_id


class TaskStatus(StrEnum):
    """Lifecycle state of an individual planned deliverable task."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    SKIPPED = "skipped"


class DeliverableTask(LimoBaseModel):
    """Individual deliverable work unit within a transformation workflow."""
    task_id: str = Field(default_factory=generate_task_id, description="Task identifier with 'task_' prefix")
    deliverable_id: str = Field(description="Referenced PlannedDeliverable ID")
    format: OutputFormat = Field(description="Target output deliverable format")
    engine_type: EngineType = Field(description="Assigned execution engine")
    is_implemented: bool = Field(description="True if engine is implemented natively in Phase D6.3")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Current execution state of this task")
    retry_count: int = Field(default=0, ge=0, description="Number of retry attempts executed")
    artifact_id: Optional[str] = Field(default=None, description="Registered Artifact ID on successful native completion")
    contract_payload: Optional[Dict[str, Any]] = Field(default=None, description="Prepared D6.3 contract payload for external engines")
    error: Optional[str] = Field(default=None, description="Safe user-facing error message (no raw tracebacks)")
    started_at: Optional[datetime] = Field(default=None, description="Execution start timestamp")
    completed_at: Optional[datetime] = Field(default=None, description="Execution finish timestamp")

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, v: str) -> str:
        if not v.startswith("task_"):
            raise ValueError("DeliverableTask ID must start with 'task_'")
        return v


class TransformationWorkflow(LimoBaseModel):
    """Execution state tracking an orchestrated transformation workflow."""
    id: str = Field(default_factory=generate_workflow_id, description="Workflow identifier with 'wf_' prefix")
    job_id: str = Field(description="Originating TransformationJob ID")
    plan_id: str = Field(description="Originating OutputPlan ID")
    canonical_id: str = Field(description="Referenced CanonicalContent ID")
    status: WorkflowStatus = Field(default=WorkflowStatus.PENDING, description="Overall workflow lifecycle state")
    tasks: Dict[str, DeliverableTask] = Field(default_factory=dict, description="Tasks keyed by deliverable_id")
    task_order: List[str] = Field(default_factory=list, description="Ordered deliverable_ids reflecting execution order")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("id")
    @classmethod
    def validate_workflow_id(cls, v: str) -> str:
        if not v.startswith("wf_"):
            raise ValueError("TransformationWorkflow ID must start with 'wf_'")
        return v


class TransformationWorkflowResult(LimoBaseModel):
    """Frozen, structured result of a transformation workflow execution handed to D6.5."""
    model_config = ConfigDict(frozen=True)

    workflow_id: str = Field(description="Originating TransformationWorkflow ID")
    job_id: str = Field(description="Originating TransformationJob ID")
    plan_id: str = Field(description="Referenced OutputPlan ID")
    canonical_id: str = Field(description="Referenced CanonicalContent ID")
    status: WorkflowStatus = Field(description="Final workflow outcome status")
    artifacts: List[Artifact] = Field(default_factory=list, description="Real artifacts created by native adapters")
    blocked_contracts: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Versioned external contract payloads held for D7/D8, keyed by deliverable_id",
    )
    failed_tasks: List[Dict[str, str]] = Field(
        default_factory=list,
        description="List of failed tasks with safe user-facing error messages",
    )
    completed_deliverable_ids: List[str] = Field(default_factory=list, description="IDs of successfully completed deliverables")
    total_deliverables: int = Field(description="Total deliverables planned in workflow")
    execution_time_seconds: float = Field(default=0.0, ge=0.0, description="Total workflow runtime in seconds")
