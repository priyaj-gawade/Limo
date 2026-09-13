"""Domain models for Phase D5.3: Normalized intermediate document representation."""

from typing import Any, Dict, List, Optional
from pydantic import Field
from ...models.base import LimoBaseModel
from ...models.enums import SourceType


class NormalizedSection(LimoBaseModel):
    """Normalized structured content section mapped from headings and paragraphs."""
    title: Optional[str] = Field(default=None, description="Section or heading title")
    level: int = Field(default=1, ge=1, le=6, description="Heading level (1 for H1, 2 for H2, etc.)")
    content: str = Field(description="Normalized textual content of this section")
    page_number: Optional[int] = Field(default=None, description="Source page number anchor")
    timestamp: Optional[str] = Field(default=None, description="Media timestamp anchor (e.g. '01:23')")


class NormalizedTable(LimoBaseModel):
    """Normalized tabular grid representation."""
    name: Optional[str] = Field(default=None, description="Table name or sheet title")
    headers: List[str] = Field(default_factory=list, description="Column header strings")
    rows: List[List[str]] = Field(default_factory=list, description="Matrix of table cell values")
    source_reference: Optional[str] = Field(default=None, description="Page, sheet, or section reference")


class NormalizedDocument(LimoBaseModel):
    """Unified normalized document representation feeding the canonicalization pipeline."""
    source_id: str = Field(description="Unique identifier of originating Source")
    source_name: str = Field(description="Original filename or URL title")
    source_type: SourceType = Field(description="Source classification")
    mime_type: str = Field(description="MIME type")
    sections: List[NormalizedSection] = Field(default_factory=list, description="Normalized sections")
    tables: List[NormalizedTable] = Field(default_factory=list, description="Normalized tables")
    raw_text: str = Field(description="Consolidated cleaned raw text")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Normalization metadata")
