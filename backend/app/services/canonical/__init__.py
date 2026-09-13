"""Canonicalization package for Limo Phase D5.4."""

from .guards import ConsistencyGuard, EvidenceGuard, PydanticGuard
from .local_extractor import (
    LocalExtractionCandidates,
    LocalStructuredExtractor,
    local_structured_extractor,
)
from .service import (
    CANONICALIZATION_VERSION,
    DEFAULT_CONFIG_HASH,
    CanonicalService,
    canonical_service,
    compute_canonical_hash,
)

__all__ = [
    "CANONICALIZATION_VERSION",
    "DEFAULT_CONFIG_HASH",
    "CanonicalService",
    "canonical_service",
    "compute_canonical_hash",
    "ConsistencyGuard",
    "EvidenceGuard",
    "PydanticGuard",
    "LocalExtractionCandidates",
    "LocalStructuredExtractor",
    "local_structured_extractor",
]
