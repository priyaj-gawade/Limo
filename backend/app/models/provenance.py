"""ValidationResult and ProvenanceRecord domain models.

Guarantees cryptographic traceability and source grounding verification across all deliverables.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import Field, field_validator
from .base import LimoBaseModel
from ..core.ids import generate_provenance_id, generate_validation_id


class CitationVerification(LimoBaseModel):
    """Mapping proving an asserted claim or data point maps directly to an ingested source."""
    claim: str = Field(description="The assertion appearing in the generated deliverable")
    source_id: str = Field(description="Ingested source ID where the supporting fact originates")
    source_hash: str = Field(description="SHA-256 hash of the supporting source document")
    citation_text: str = Field(description="Exact snippet or excerpt validating the claim")
    similarity_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Semantic or string similarity score")


class ValidationResult(LimoBaseModel):
    """Automated factual accuracy and citation verification report for an artifact."""

    id: str = Field(default_factory=generate_validation_id, description="Stable validation ID with 'val_' prefix")
    artifact_id: str = Field(description="Verified Artifact ID")
    is_valid: bool = Field(description="True if quality score meets or exceeds standard threshold (>=0.70) and no critical errors exist")
    score: float = Field(
        ge=0.0,
        le=1.0,
        description="Standardized factuality and citation confidence score between 0.0 and 1.0 (standard pass threshold: >=0.70)"
    )
    hallucination_check_passed: bool = Field(
        default=True,
        description="True if zero unsupported factual claims were detected"
    )
    citations_verified: List[CitationVerification] = Field(
        default_factory=list,
        description="List of verified claim-to-source provenance mappings"
    )
    warnings: List[str] = Field(default_factory=list, description="Non-critical quality or formatting notices")
    errors: List[str] = Field(default_factory=list, description="Critical factual discrepancies or ungrounded claims")
    validated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC verification timestamp"
    )

    @field_validator("id")
    @classmethod
    def validate_validation_id(cls, v: str) -> str:
        if not v.startswith("val_"):
            raise ValueError("ValidationResult ID must start with 'val_'")
        return v


class ProvenanceRecord(LimoBaseModel):
    """Tamper-evident cryptographic provenance ledger record for verifiable integrity."""

    id: str = Field(default_factory=generate_provenance_id, description="Stable provenance ID with 'prov_' prefix")
    artifact_id: str = Field(description="Originating Artifact ID")
    artifact_hash: str = Field(
        min_length=64,
        max_length=64,
        description="SHA-256 hash of the generated deliverable binary/text"
    )
    source_hashes: List[str] = Field(
        min_length=1,
        description="List of SHA-256 hashes of all input sources consumed during generation"
    )
    canonical_content_hash: Optional[str] = Field(
        default=None,
        min_length=64,
        max_length=64,
        description="SHA-256 hash of the intermediate CanonicalContent representation"
    )
    transformation_job_id: Optional[str] = Field(default=None, description="Generating TransformationJob ID")
    generator_name: str = Field(description="Generator engine or pipeline identifier (e.g. 'GenOffice.SlideDeckGenerator')")
    model_version: str = Field(description="Model or engine version utilized during generation")
    signature: Optional[str] = Field(default=None, description="Optional cryptographic signature of the manifest")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC ledger registration timestamp"
    )

    @field_validator("id")
    @classmethod
    def validate_provenance_id(cls, v: str) -> str:
        if not v.startswith("prov_"):
            raise ValueError("ProvenanceRecord ID must start with 'prov_'")
        return v

    @field_validator("artifact_hash")
    @classmethod
    def validate_artifact_hash(cls, v: str) -> str:
        if len(v) != 64 or not all(c in "0123456789abcdefABCDEF" for c in v):
            raise ValueError("Artifact hash must be a valid 64-character hexadecimal SHA-256 digest")
        return v.lower()

    @field_validator("canonical_content_hash")
    @classmethod
    def validate_canonical_hash(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if len(v) != 64 or not all(c in "0123456789abcdefABCDEF" for c in v):
                raise ValueError("Canonical content hash must be a valid 64-character hexadecimal SHA-256 digest")
            return v.lower()
        return v
