"""Extraction orchestration service."""

from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, Optional, Tuple

from ...db.connection import get_connection
from ...db.repositories.source_repo import SourceRepository
from ...exceptions import StorageError
from ...models.project import Source
from ...storage.service import StorageService, storage_service
from .constants import (
    DEFAULT_CONFIG_HASH,
    EXTRACTION_VERSION,
    compute_extraction_cache_key,
)
from .models import ExtractedDocument, ExtractionSummaryResponse
from .registry import ExtractorRegistry, extractor_registry

logger = logging.getLogger("limo.services.extraction.service")


class ExtractionError(StorageError):
    """Raised when source content extraction fails or format is unsupported."""
    pass


class ExtractionService:
    """Orchestrates document and media extraction using registered extractors."""

    def __init__(
        self,
        registry: Optional[ExtractorRegistry] = None,
        db_path: Optional[str] = None,
        storage: Optional[StorageService] = None,
    ):
        self.registry = registry or extractor_registry
        self.db_path = db_path
        self.storage = storage or storage_service

    async def extract_source(
        self,
        source: Source,
        content: Optional[bytes] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> ExtractedDocument:
        """Select appropriate extractor, execute extraction, and record extraction metadata."""
        extra_meta = extra_metadata or {}
        model_id = extra_meta.get("model_id") or source.metadata.get("model_id", "default")
        config_hash = extra_meta.get("config_hash") or source.metadata.get("config_hash", DEFAULT_CONFIG_HASH)

        composite_cache_key = compute_extraction_cache_key(
            source_hash=source.content_hash,
            extraction_version=EXTRACTION_VERSION,
            model_id=model_id,
            config_hash=config_hash,
        )

        # Check 4-part cache key hit
        cached_doc = self.get_cached_extraction(source.id, expected_cache_key=composite_cache_key)
        if cached_doc:
            logger.info("Extraction cache hit for source '%s' (cache_key: %s)", source.id, composite_cache_key)
            cached_doc.metadata["cache_hit"] = True
            return cached_doc

        try:
            extractor = self.registry.get_extractor(source.mime_type, source.name)
        except Exception as e:
            raise ExtractionError(f"No suitable extractor registered for '{source.name}': {e}") from e

        logger.info(
            "Extracting source '%s' (id: %s) using %s",
            source.name,
            source.id,
            extractor.__class__.__name__,
        )

        # Resolve file path on disk if available to support disk streaming without RAM overhead
        file_path = None
        if source.storage_ref and self.storage.file_exists(source.storage_ref):
            file_path = self.storage.safe_resolve(source.storage_ref)

        merged_metadata = {**source.metadata, **extra_meta}
        doc = await extractor.extract(
            source_id=source.id,
            filename=source.name,
            file_path=file_path,
            content=content,
            metadata=merged_metadata,
        )

        # Inject standard 4-part versioning metadata
        doc.metadata["composite_cache_key"] = composite_cache_key
        doc.metadata["extraction_version"] = EXTRACTION_VERSION
        doc.metadata["model_id"] = model_id
        doc.metadata["config_hash"] = config_hash
        doc.metadata["source_hash"] = source.content_hash
        doc.metadata["extracted_at"] = datetime.now(timezone.utc).isoformat()
        doc.metadata["extractor_name"] = extractor.__class__.__name__

        # Persist full extraction JSON artifact to sandboxed storage
        try:
            self.storage.save_extraction_file(source.id, doc.model_dump_json().encode("utf-8"))
        except Exception as e:
            logger.warning("Failed to save extraction artifact for source '%s': %s", source.id, e)

        # Persist extracted_text and metadata update back to database
        try:
            with get_connection(self.db_path) as conn:
                updated_meta = {**source.metadata, **doc.metadata}
                SourceRepository.update_source_metadata(
                    conn,
                    source_id=source.id,
                    metadata=updated_meta,
                    extracted_text=doc.raw_text,
                )
        except Exception as e:
            logger.warning("Failed to update source database record with extracted text: %s", e)

        doc.metadata["cache_hit"] = False
        return doc

    def get_cached_extraction(
        self,
        source_id: str,
        expected_cache_key: Optional[str] = None,
    ) -> Optional[ExtractedDocument]:
        """Retrieve stored extraction from storage, optionally verifying composite cache key."""
        storage_ref = f"extractions/{source_id}.json"
        if not self.storage.file_exists(storage_ref):
            return None

        try:
            raw_bytes = self.storage.read_file(storage_ref)
            doc = ExtractedDocument.model_validate_json(raw_bytes)
            if expected_cache_key:
                stored_key = doc.metadata.get("composite_cache_key")
                if stored_key != expected_cache_key:
                    return None
            return doc
        except Exception as e:
            logger.warning("Failed to read extraction file for '%s': %s", source_id, e)
            return None

    def build_summary_response(
        self,
        doc: ExtractedDocument,
        cache_hit: Optional[bool] = None,
    ) -> ExtractionSummaryResponse:
        """Construct lightweight API response from an ExtractedDocument."""
        effective_cache_hit = cache_hit if cache_hit is not None else doc.metadata.get("cache_hit", False)
        metrics = {
            "page_count": doc.metadata.get("page_count", 1),
            "heading_count": len(doc.headings),
            "paragraph_count": len(doc.paragraphs),
            "table_count": len(doc.tables),
            "media_count": len(doc.media_items),
            "raw_text_length": len(doc.raw_text),
        }
        parts = []
        if metrics["page_count"] > 1:
            parts.append(f"{metrics['page_count']} pages")
        if metrics["heading_count"]:
            parts.append(f"{metrics['heading_count']} headings")
        if metrics["paragraph_count"]:
            parts.append(f"{metrics['paragraph_count']} paragraphs")
        if metrics["table_count"]:
            parts.append(f"{metrics['table_count']} tables")
        if metrics["media_count"]:
            parts.append(f"{metrics['media_count']} media items")

        summary_text = "Extracted " + (", ".join(parts) if parts else "plain text content")

        return ExtractionSummaryResponse(
            source_id=doc.source_id,
            extraction_id=f"ext_{doc.source_id}",
            status="completed",
            cache_hit=effective_cache_hit,
            summary=summary_text,
            metrics=metrics,
            extracted_at=doc.metadata.get("extracted_at", datetime.now(timezone.utc).isoformat()),
        )


extraction_service = ExtractionService()
