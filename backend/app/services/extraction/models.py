"""Extraction intermediate data models.

Preserves structured evidence (headings, paragraphs, tables, media items, transcripts)
extracted from raw sources prior to normalization and canonicalization.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from ...models.enums import SourceType


class ExtractedHeading(BaseModel):
    """Document section heading with structural level and location marker."""
    text: str = Field(min_length=1, description="Heading text")
    level: int = Field(default=1, ge=1, le=6, description="Heading depth level (1=H1 ... 6=H6)")
    page_number: Optional[int] = Field(default=None, ge=1, description="Originating page number if paged")
    timestamp: Optional[str] = Field(default=None, description="Timestamp anchor (e.g. '04:12') if media")


class ExtractedParagraph(BaseModel):
    """Extracted text block with contextual location metadata."""
    text: str = Field(min_length=1, description="Paragraph body text")
    section_title: Optional[str] = Field(default=None, description="Enclosing heading text")
    page_number: Optional[int] = Field(default=None, ge=1, description="Originating page number")
    timestamp: Optional[str] = Field(default=None, description="Timestamp anchor if media")


class ExtractedTable(BaseModel):
    """Tabular grid extracted with headers, row cells, and origin reference."""
    name: Optional[str] = Field(default=None, description="Table title, caption, or sheet name")
    headers: List[str] = Field(default_factory=list, description="Column header labels")
    rows: List[List[str]] = Field(default_factory=list, description="Row cell contents")
    page_number: Optional[int] = Field(default=None, ge=1, description="Originating page number")


class ExtractedMediaItem(BaseModel):
    """Visual or auditory evidence extracted from media sources."""
    media_type: str = Field(description="Classification: 'video_chapter', 'audio_segment', 'image', 'diagram'")
    timestamp_or_bounds: Optional[str] = Field(default=None, description="Time range or spatial coordinates")
    labels: List[str] = Field(default_factory=list, description="Categorical tags or detected elements")
    transcript: Optional[str] = Field(default=None, description="Transcript with timestamps (not guaranteed verbatim)")
    summary: Optional[str] = Field(default=None, description="Optional high-level overview if generated")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary technical metadata")


class ExtractedDocument(BaseModel):
    """Unified container for all raw structured evidence extracted from a source asset."""
    source_id: str = Field(description="Unique identifier of the originating Source asset")
    source_name: str = Field(description="Original filename or resource title")
    source_type: SourceType = Field(description="Class of the source")
    mime_type: str = Field(description="MIME content type")
    headings: List[ExtractedHeading] = Field(default_factory=list, description="Identified section headings")
    paragraphs: List[ExtractedParagraph] = Field(default_factory=list, description="Body paragraphs")
    tables: List[ExtractedTable] = Field(default_factory=list, description="Structured tables")
    media_items: List[ExtractedMediaItem] = Field(default_factory=list, description="Media clips, scenes, or figures")
    raw_text: str = Field(description="Full consolidated text extraction")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Extractor-specific diagnostic metadata")


class ExtractionSummaryResponse(BaseModel):
    """Lightweight extraction summary returned by REST API."""
    source_id: str = Field(description="Originating source ID")
    extraction_id: str = Field(description="Unique extraction ID")
    status: str = Field(default="completed", description="Lifecycle status of extraction")
    cache_hit: bool = Field(default=False, description="Whether result was retrieved from cache")
    summary: str = Field(description="Brief human-readable summary of extracted contents")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Structural extraction counts and measurements")
    extracted_at: str = Field(description="UTC timestamp of extraction")
