"""Transformation lifecycle event domain models (Phase D6.5).

Defines public, frontend-safe lifecycle events with strictly monotonic per-job
sequence ordering for real-time tracking, reconnection, and SSE stream formatting.
"""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Dict
from pydantic import Field, field_validator
from .base import LimoBaseModel
from ..core.ids import generate_event_id


class TransformationEventType(StrEnum):
    """Lifecycle event types for transformation workflow tracking."""

    JOB_CREATED = "job.created"
    JOB_STARTED = "job.started"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    ARTIFACT_CREATED = "artifact.created"
    TASK_FAILED = "task.failed"
    JOB_WAITING_EXTERNAL = "job.waiting_external"
    JOB_PARTIALLY_COMPLETED = "job.partially_completed"
    JOB_COMPLETED = "job.completed"
    JOB_FAILED = "job.failed"
    JOB_CANCELLED = "job.cancelled"


class TransformationLifecycleEvent(LimoBaseModel):
    """Safe public event dispatched during transformation workflow execution."""

    event_id: str = Field(
        default_factory=generate_event_id,
        description="Stable event ID with 'evt_' prefix",
    )
    sequence: int = Field(
        ge=1,
        description="Strictly monotonic sequence number scoped to job_id",
    )
    job_id: str = Field(description="Target TransformationJob ID with 'job_' prefix")
    event_type: TransformationEventType = Field(description="Lifecycle event discriminator")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC event creation timestamp",
    )
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Safe public metadata payload (strictly zero private CoT or secrets)",
    )

    @field_validator("event_id")
    @classmethod
    def validate_event_id(cls, v: str) -> str:
        if not v.startswith("evt_"):
            raise ValueError("TransformationLifecycleEvent ID must start with 'evt_'")
        return v

    @field_validator("job_id")
    @classmethod
    def validate_job_id(cls, v: str) -> str:
        if not v.startswith("job_"):
            raise ValueError("Target job_id must start with 'job_'")
        return v

    @property
    def id(self) -> str:
        """Alias to event_id for consistency across models."""
        return self.event_id

    def to_sse_frame(self) -> str:
        """Serialize event to standard Server-Sent Events (SSE) text frame format."""
        data_json = self.model_dump_json()
        return f"id: {self.event_id}\nevent: {self.event_type.value}\ndata: {data_json}\n\n"
