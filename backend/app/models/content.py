"""Canonical Content domain model.

The core original engineering component of Limo that converts raw ingested multi-modal
sources into one structured, verified representation used by every output generator.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import Field, field_validator
from .base import LimoBaseModel
from ..core.ids import generate_canonical_id


class CanonicalEntity(LimoBaseModel):
    """Named entity identified across ingested sources."""
    name: str = Field(description="Entity name")
    category: str = Field(description="Entity classification (e.g. 'Organization', 'Person', 'System', 'Threat')")
    description: Optional[str] = Field(default=None, description="Contextual description")
    relevance_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Salience to core narrative")
    aliases: List[str] = Field(default_factory=list, description="Known aliases, acronyms, or alternate names")
    source_reference: Optional[str] = Field(default=None, description="Originating section, page, or context reference")


class CanonicalFact(LimoBaseModel):
    """Factual assertion grounded in source material."""
    statement: str = Field(description="Grounded factual assertion")
    source_id: Optional[str] = Field(default=None, description="Originating Source ID")
    source_reference: Optional[str] = Field(default=None, description="Page, section, or timestamp reference")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Model-assessed verification confidence")
    evidence_status: str = Field(default="unverified", description="Deterministic evidence status: 'verified', 'weak', or 'unverified'")
    evidence_score: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Deterministic lexical/anchor evidence overlap score")


class CanonicalClaim(LimoBaseModel):
    """Specific argument, thesis, or claim asserted in sources."""
    claim: str = Field(description="The asserted proposition or argument")
    claimant: Optional[str] = Field(default=None, description="Person or entity making the assertion")
    evidence: Optional[str] = Field(default=None, description="Supporting evidence cited")


class CanonicalEvent(LimoBaseModel):
    """Chronological event or timeline milestone."""
    title: str = Field(description="Event summary")
    timestamp_desc: Optional[str] = Field(default=None, description="Date, timestamp or relative timeframe")
    significance: Optional[str] = Field(default=None, description="Impact or relevance to narrative")


class CanonicalDataPoint(LimoBaseModel):
    """Structured metric, statistic, or quantitative finding."""
    metric: str = Field(description="Name of metric (e.g. 'Telemetry spoofing incidents')")
    value: str = Field(description="Quantitative value (e.g. '142', '9.4%')")
    unit: Optional[str] = Field(default=None, description="Measurement unit")
    context: Optional[str] = Field(default=None, description="Qualifying context or timeframe")


class CanonicalReference(LimoBaseModel):
    """Citation or reference to external documents or source sections."""
    citation_key: str = Field(description="Citation tag (e.g. '[REF-1]')")
    title: str = Field(description="Referenced document or artifact title")
    uri_or_location: Optional[str] = Field(default=None, description="URI, path, or page reference")


class CanonicalIntent(LimoBaseModel):
    """Strategic context, audience objectives, and core takeaway."""
    primary_purpose: str = Field(description="Primary objective (e.g. 'Alert executive leadership to zero-day anomaly')")
    target_audiences: List[str] = Field(default_factory=list, description="Intended recipient profiles")
    core_narrative: str = Field(description="Core takeaway or central synthesis thesis")
    urgency_level: Optional[str] = Field(default=None, description="E.g. 'Immediate', 'Strategic', 'Informational'")


class CanonicalContent(LimoBaseModel):
    """Unified intermediate structured model extracted from multi-modal sources."""

    id: str = Field(default_factory=generate_canonical_id, description="Stable ID with 'can_' prefix")
    source_ids: List[str] = Field(min_length=1, description="List of ingested Source IDs synthesized into this model")
    title: str = Field(min_length=1, max_length=255, description="Overarching synthesis title")
    context: str = Field(description="Broad situational context, background, and environmental setting")
    intent: CanonicalIntent = Field(description="Structured communication intent and audience objectives")
    entities: List[CanonicalEntity] = Field(default_factory=list, description="Extracted domain entities")
    facts: List[CanonicalFact] = Field(default_factory=list, description="Extracted factual claims with source grounding")
    claims: List[CanonicalClaim] = Field(default_factory=list, description="Identified arguments and qualitative claims")
    events: List[CanonicalEvent] = Field(default_factory=list, description="Chronological timeline of events")
    data_points: List[CanonicalDataPoint] = Field(default_factory=list, description="Structured quantitative metrics")
    recommendations: List[str] = Field(default_factory=list, description="Actionable recommendations derived from context")
    references: List[CanonicalReference] = Field(default_factory=list, description="Verifiable citations")
    content_hash: str = Field(
        min_length=64,
        max_length=64,
        description="Cryptographic SHA-256 hash of the canonical structure ensuring provenance tracking"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC synthesis timestamp"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary engine metadata")

    @field_validator("id")
    @classmethod
    def validate_canonical_id(cls, v: str) -> str:
        if not v.startswith("can_"):
            raise ValueError("CanonicalContent ID must start with 'can_'")
        return v

    @field_validator("content_hash")
    @classmethod
    def validate_sha256(cls, v: str) -> str:
        if len(v) != 64 or not all(c in "0123456789abcdefABCDEF" for c in v):
            raise ValueError("Content hash must be a valid 64-character hexadecimal SHA-256 digest")
        return v.lower()

    # Aliases for content_hash / provenance tracking
    canonical_hash = canonical_fingerprint = property(lambda self: self.content_hash)

