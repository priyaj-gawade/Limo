"""Project and Source domain models."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import Field, field_validator
from .base import LimoBaseModel
from .enums import SourceType
from ..core.ids import generate_project_id, generate_source_id


class Project(LimoBaseModel):
    """Container grouping ingested sources, chats, and transformed deliverables."""

    id: str = Field(default_factory=generate_project_id, description="Stable project ID with 'proj_' prefix")
    name: str = Field(min_length=1, max_length=255, description="Human-readable project title")
    description: Optional[str] = Field(default=None, max_length=2000, description="Optional project summary or goal")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC last modification timestamp"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary extension metadata")

    @field_validator("id")
    @classmethod
    def validate_project_id(cls, v: str) -> str:
        if not v.startswith("proj_"):
            raise ValueError("Project ID must start with 'proj_'")
        return v


class Source(LimoBaseModel):
    """Raw ingested file, document, or media asset associated with a project."""

    id: str = Field(default_factory=generate_source_id, description="Stable source ID with 'src_' prefix")
    project_id: Optional[str] = Field(default=None, description="Associated project ID")
    name: str = Field(min_length=1, max_length=255, description="Original filename or resource title")
    source_type: SourceType = Field(description="Classification of the ingested source asset")
    mime_type: str = Field(min_length=1, max_length=128, description="Standard MIME content type")
    storage_ref: Optional[str] = Field(
        default=None,
        description="Internal storage reference key within approved storage boundaries (not a trusted client path)"
    )
    size_bytes: int = Field(ge=0, description="File size in bytes")
    content_hash: str = Field(
        min_length=64,
        max_length=64,
        description="Cryptographic SHA-256 hash of the source content for tamper-evident tracking"
    )
    extracted_text: Optional[str] = Field(default=None, description="Extracted raw textual content if available")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC ingestion timestamp"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary extraction metadata")

    @field_validator("id")
    @classmethod
    def validate_source_id(cls, v: str) -> str:
        if not v.startswith("src_"):
            raise ValueError("Source ID must start with 'src_'")
        return v

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, v: str) -> str:
        if len(v) != 64 or not all(c in "0123456789abcdefABCDEF" for c in v):
            raise ValueError("content_hash must be a valid 64-character hexadecimal SHA-256 hash")
        return v.lower()
