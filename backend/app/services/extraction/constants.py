"""Extraction engine constants and cache key utilities."""

import hashlib

from typing import Optional

EXTRACTION_VERSION = "ext_v1.0.0"

# Default configuration hash representing standard extractor prompt templates and parameters
DEFAULT_CONFIG_HASH = hashlib.sha256(b"limo_default_extraction_config_v1").hexdigest()[:16]


def compute_extraction_cache_key(
    source_hash: str = "",
    content_hash: Optional[str] = None,
    extraction_version: str = EXTRACTION_VERSION,
    model_id: str = "default",
    config_hash: str = DEFAULT_CONFIG_HASH,
) -> str:
    """Compute deterministic composite cache key from 4-part tuple.

    Formula: sha256(source_hash:extraction_version:model_id:config_hash)
    """
    effective_hash = content_hash if content_hash is not None else source_hash
    raw_key = f"{effective_hash}:{extraction_version}:{model_id}:{config_hash}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

