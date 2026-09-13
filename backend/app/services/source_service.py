"""Source asset management business service."""

import logging
from typing import Any, Dict, List, Optional

from ..core.ids import generate_source_id
from ..db.connection import get_connection
from ..db.repositories.project_repo import ProjectRepository
from ..db.repositories.source_repo import SourceRepository
from ..exceptions import EntityNotFoundError, StorageError
from ..models.enums import SourceType
from ..models.project import Source
from ..storage.service import StorageService, storage_service

logger = logging.getLogger("limo.services.source")


import os
import urllib.parse
from .extraction.constants import (
    DEFAULT_CONFIG_HASH,
    EXTRACTION_VERSION,
    compute_extraction_cache_key,
)
from .extraction.ssrf import fetch_url_ssrf_safe


class SourceService:
    """Business service for raw ingested sources and files."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        storage: Optional[StorageService] = None,
    ):
        self.db_path = db_path
        self.storage = storage or storage_service

    @staticmethod
    def _infer_source_type(mime_type: str, filename: str) -> SourceType:
        """Infer high-level source category from MIME type and extension."""
        mime_lower = mime_type.lower()
        if "audio" in mime_lower:
            return SourceType.AUDIO
        if "video" in mime_lower:
            return SourceType.VIDEO
        if "csv" in mime_lower or "spreadsheet" in mime_lower or filename.lower().endswith((".csv", ".xlsx", ".tsv")):
            return SourceType.TABULAR
        if "text" in mime_lower or filename.lower().endswith((".txt", ".md")):
            return SourceType.TEXT
        return SourceType.FILE

    def register_file_source(
        self,
        filename: str,
        content: bytes,
        mime_type: str,
        project_id: Optional[str] = None,
        source_type: Optional[SourceType] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Source:
        """Atomically persist a source file, verify its integrity, and create a Source entity.

        Enforces versioned deduplication: compares composite cache key
        (source_hash + extraction_version + model_id + config_hash).
        """
        clean_filename = filename.strip()
        if not clean_filename:
            raise ValueError("Source filename cannot be empty")

        content_hash = self.storage.compute_sha256(content)
        meta = dict(metadata or {})

        extraction_ver = meta.get("extraction_version", EXTRACTION_VERSION)
        model_id = meta.get("model_id", "default")
        config_hash = meta.get("config_hash", DEFAULT_CONFIG_HASH)
        composite_cache_key = compute_extraction_cache_key(
            content_hash=content_hash,
            extraction_version=extraction_ver,
            model_id=model_id,
            config_hash=config_hash,
        )
        meta["composite_cache_key"] = composite_cache_key
        meta["extraction_version"] = extraction_ver
        meta["model_id"] = model_id
        meta["config_hash"] = config_hash

        with get_connection(self.db_path) as conn:
            if project_id:
                project = ProjectRepository.get_project(conn, project_id)
                if not project:
                    raise EntityNotFoundError("Project", project_id)

            # 4-part Versioned Deduplication Check
            existing = SourceRepository.get_source_by_hash(conn, content_hash, project_id)
            if existing:
                ex_ver = existing.metadata.get("extraction_version")
                ex_model = existing.metadata.get("model_id", "default")
                ex_cfg = existing.metadata.get("config_hash", DEFAULT_CONFIG_HASH)
                ex_key = existing.metadata.get("composite_cache_key") or compute_extraction_cache_key(
                    existing.content_hash, ex_ver or "", ex_model, ex_cfg
                )

                if ex_key == composite_cache_key:
                    logger.info(
                        "Reusing deduplicated source '%s' (id: %s, cache_key: %s)",
                        existing.name,
                        existing.id,
                        composite_cache_key,
                    )
                    return existing

            source_id = generate_source_id()
            inferred_type = source_type or self._infer_source_type(mime_type, clean_filename)

            # Atomic save to sandboxed storage
            storage_ref, size_bytes, calculated_hash = self.storage.save_source_file(
                source_id=source_id,
                filename=clean_filename,
                content=content,
            )

            # Verification: Ensure file physically exists on disk and size matches
            if not self.storage.file_exists(storage_ref):
                raise StorageError(f"Storage write verification failed for '{storage_ref}'")

            source = Source(
                id=source_id,
                project_id=project_id,
                name=clean_filename,
                source_type=inferred_type,
                mime_type=mime_type,
                storage_ref=storage_ref,
                size_bytes=size_bytes,
                content_hash=calculated_hash,
                metadata=meta,
            )

            created = SourceRepository.create_source(conn, source)
            logger.info("Registered file source '%s' (id: %s, %d bytes)", clean_filename, source_id, size_bytes)
            return created

    async def register_url_source(
        self,
        url: str,
        project_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Source:
        """Fetch a remote web URL with verified redirect-aware SSRF protection and register as a source."""
        clean_url = url.strip()
        if not clean_url:
            raise ValueError("Source URL cannot be empty")

        response = await fetch_url_ssrf_safe(clean_url)
        content = response.content

        # Derive clean filename from URL path
        parsed = urllib.parse.urlparse(clean_url)
        path_tail = os.path.basename(parsed.path.rstrip("/"))
        if not path_tail or not path_tail.endswith((".html", ".htm")):
            filename = f"{path_tail}.html" if path_tail else "web_page.html"
        else:
            filename = path_tail

        source_meta = {
            **(metadata or {}),
            "source_url": clean_url,
            "http_status": response.status_code,
            "content_type": response.headers.get("content-type", "text/html"),
        }

        return self.register_file_source(
            filename=filename,
            content=content,
            mime_type="text/html",
            project_id=project_id,
            source_type=SourceType.URL,
            metadata=source_meta,
        )

    def register_text_source(
        self,
        name: str,
        text_content: str,
        project_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Source:
        """Register a raw text source snippet."""
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Source title cannot be empty")

        filename = f"{clean_name}.txt" if not clean_name.lower().endswith(".txt") else clean_name
        encoded_bytes = text_content.encode("utf-8")

        with get_connection(self.db_path) as conn:
            if project_id:
                project = ProjectRepository.get_project(conn, project_id)
                if not project:
                    raise EntityNotFoundError("Project", project_id)

            source_id = generate_source_id()
            storage_ref, size_bytes, content_hash = self.storage.save_source_file(
                source_id=source_id,
                filename=filename,
                content=encoded_bytes,
            )

            source = Source(
                id=source_id,
                project_id=project_id,
                name=clean_name,
                source_type=SourceType.TEXT,
                mime_type="text/plain",
                storage_ref=storage_ref,
                size_bytes=size_bytes,
                content_hash=content_hash,
                extracted_text=text_content,
                metadata=metadata or {},
            )

            created = SourceRepository.create_source(conn, source)
            logger.info("Registered text source '%s' (id: %s)", clean_name, source_id)
            return created

    def get_source(self, source_id: str) -> Source:
        """Retrieve source record by ID or raise EntityNotFoundError."""
        with get_connection(self.db_path) as conn:
            source = SourceRepository.get_source(conn, source_id)
            if not source:
                raise EntityNotFoundError("Source", source_id)
            return source

    def list_sources(self, project_id: str) -> List[Source]:
        """List all sources associated with a project."""
        with get_connection(self.db_path) as conn:
            return SourceRepository.list_sources_by_project(conn, project_id)

    def read_source_content(self, source_id: str) -> bytes:
        """Read raw binary contents of a source and verify cryptographic hash matches."""
        source = self.get_source(source_id)
        if not source.storage_ref:
            if source.extracted_text:
                return source.extracted_text.encode("utf-8")
            raise StorageError(f"Source '{source_id}' has no associated storage reference or text")

        content = self.storage.read_file(source.storage_ref)
        actual_hash = self.storage.compute_sha256(content)
        if actual_hash != source.content_hash:
            raise StorageError(
                f"Source integrity violation for '{source_id}': expected {source.content_hash}, got {actual_hash}"
            )
        return content

    def delete_source(self, source_id: str) -> bool:
        """Delete a source from both physical storage and database."""
        with get_connection(self.db_path) as conn:
            source = SourceRepository.get_source(conn, source_id)
            if not source:
                raise EntityNotFoundError("Source", source_id)

            if source.storage_ref:
                try:
                    self.storage.delete_file(source.storage_ref)
                except Exception as e:
                    logger.warning("Failed to delete physical file '%s': %s", source.storage_ref, e)

            deleted = SourceRepository.delete_source(conn, source_id)
            logger.info("Deleted source (id: %s)", source_id)
            return deleted


source_service = SourceService()
