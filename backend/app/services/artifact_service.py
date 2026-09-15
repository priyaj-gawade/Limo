"""Artifact entity lifecycle, storage verification, and provenance business service."""

import logging
from typing import Any, Dict, List, Optional

from ..db.connection import get_connection
from ..db.repositories.artifact_repo import ArtifactRepository
from ..db.repositories.job_repo import JobRepository
from ..db.repositories.project_repo import ProjectRepository
from ..exceptions import EntityNotFoundError, StorageError
from ..models.artifact import Artifact, ArtifactVersion
from ..models.enums import ArtifactType, ValidationStatus
from ..models.provenance import CitationVerification, ProvenanceRecord, ValidationResult
from ..storage.service import StorageService, storage_service

logger = logging.getLogger("limo.services.artifact")


class ArtifactService:
    """Business service for first-class deliverable artifacts, versions, and integrity."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        storage: Optional[StorageService] = None,
    ):
        self.db_path = db_path
        self.storage = storage or storage_service

    def register_artifact(
        self,
        title: str,
        artifact_type: ArtifactType,
        file_format: str,
        storage_ref: str,
        project_id: Optional[str] = None,
        job_id: Optional[str] = None,
        description: Optional[str] = None,
        stats: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        artifact_id: Optional[str] = None,
    ) -> Artifact:
        """Register a deliverable artifact.

        Strict integrity enforcement:
        1. storage_ref is resolved safely within sandbox boundaries.
        2. The referenced file MUST physically exist on disk before registration.
        3. SHA-256 hash and byte size are computed directly from the real file.
        """
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("Artifact title cannot be empty")

        clean_ref = storage_ref.strip()
        if not clean_ref:
            raise ValueError("Artifact storage_ref cannot be empty")

        # Normalize format extension (e.g. 'docx' -> '.docx')
        fmt = file_format.strip().lower()
        if not fmt.startswith("."):
            fmt = f".{fmt}"

        # 1 & 2. Verify file physically exists in sandboxed storage
        if not self.storage.file_exists(clean_ref):
            raise StorageError(
                f"Referenced artifact file does not exist in storage: '{clean_ref}'"
            )

        # 3. Read physical file to verify hash and byte count
        file_bytes = self.storage.read_file(clean_ref)
        content_hash = self.storage.compute_sha256(file_bytes)
        size_bytes = len(file_bytes)

        with get_connection(self.db_path) as conn:
            if project_id:
                project = ProjectRepository.get_project(conn, project_id)
                if not project:
                    raise EntityNotFoundError("Project", project_id)

            if job_id:
                job = JobRepository.get_job(conn, job_id)
                if not job:
                    raise EntityNotFoundError("TransformationJob", job_id)

            artifact_kwargs = {
                "project_id": project_id,
                "job_id": job_id,
                "title": clean_title,
                "artifact_type": artifact_type,
                "file_format": fmt,
                "storage_ref": clean_ref,
                "size_bytes": size_bytes,
                "content_hash": content_hash,
                "description": description.strip() if description else None,
                "stats": stats.strip() if stats else None,
                "version": 1,
                "validation_status": ValidationStatus.PENDING,
                "metadata": metadata or {},
            }
            if artifact_id:
                artifact_kwargs["id"] = artifact_id

            artifact = Artifact(**artifact_kwargs)
            created = ArtifactRepository.create_artifact(conn, artifact)

            # Record initial v1 snapshot in artifact_versions
            initial_version = ArtifactVersion(
                artifact_id=created.id,
                version_number=1,
                storage_ref=clean_ref,
                size_bytes=size_bytes,
                content_hash=content_hash,
                change_summary="Initial deliverable",
            )
            ArtifactRepository.create_artifact_version(conn, initial_version)

            logger.info(
                "Registered artifact '%s' (id: %s, type: %s, %d bytes, sha256: %s)",
                clean_title,
                created.id,
                artifact_type.value,
                size_bytes,
                content_hash[:8],
            )
            return created

    def get_artifact(self, artifact_id: str) -> Artifact:
        """Retrieve an artifact by ID or raise EntityNotFoundError."""
        with get_connection(self.db_path) as conn:
            artifact = ArtifactRepository.get_artifact(conn, artifact_id)
            if not artifact:
                raise EntityNotFoundError("Artifact", artifact_id)
            return artifact

    def update_artifact_metadata(self, artifact_id: str, metadata: Dict[str, Any]) -> bool:
        """Update artifact metadata in SQLite."""
        with get_connection(self.db_path) as conn:
            artifact = ArtifactRepository.get_artifact(conn, artifact_id)
            if not artifact:
                raise EntityNotFoundError("Artifact", artifact_id)
            return ArtifactRepository.update_artifact_metadata(conn, artifact_id, metadata)

    def list_artifacts(
        self,
        project_id: Optional[str] = None,
        job_id: Optional[str] = None,
        artifact_type: Optional[ArtifactType] = None,
    ) -> List[Artifact]:
        """List artifacts with optional filtering by project, job, or deliverable type."""
        with get_connection(self.db_path) as conn:
            return ArtifactRepository.list_artifacts(
                conn,
                project_id=project_id,
                job_id=job_id,
                artifact_type=artifact_type,
            )

    def read_artifact_content(self, artifact_id: str) -> bytes:
        """Read raw binary deliverable content and verify cryptographic SHA-256 integrity."""
        artifact = self.get_artifact(artifact_id)
        content_bytes = self.storage.read_file(artifact.storage_ref)
        actual_hash = self.storage.compute_sha256(content_bytes)

        if actual_hash != artifact.content_hash:
            raise StorageError(
                f"Cryptographic hash mismatch for artifact '{artifact_id}': "
                f"expected {artifact.content_hash}, got {actual_hash}"
            )
        return content_bytes

    def create_artifact_version(
        self,
        artifact_id: str,
        storage_ref: str,
        change_summary: Optional[str] = None,
    ) -> ArtifactVersion:
        """Create a new historical revision snapshot for an existing artifact.

        Uses COALESCE(MAX(version_number), 0) + 1 inside a transaction.
        Enforces physical file existence before recording the revision.
        """
        clean_ref = storage_ref.strip()
        if not clean_ref:
            raise ValueError("Revision storage_ref cannot be empty")

        if not self.storage.file_exists(clean_ref):
            raise StorageError(
                f"Referenced revision file does not exist in storage: '{clean_ref}'"
            )

        file_bytes = self.storage.read_file(clean_ref)
        content_hash = self.storage.compute_sha256(file_bytes)
        size_bytes = len(file_bytes)

        with get_connection(self.db_path) as conn:
            artifact = ArtifactRepository.get_artifact(conn, artifact_id)
            if not artifact:
                raise EntityNotFoundError("Artifact", artifact_id)

            # Monotonic next version using MAX(version_number) + 1
            next_version = ArtifactRepository.get_next_version_number(conn, artifact_id)

            version = ArtifactVersion(
                artifact_id=artifact_id,
                version_number=next_version,
                storage_ref=clean_ref,
                size_bytes=size_bytes,
                content_hash=content_hash,
                change_summary=change_summary.strip() if change_summary else None,
            )
            created_version = ArtifactRepository.create_artifact_version(conn, version)

            # Update parent artifact pointer
            ArtifactRepository.update_artifact_version(
                conn,
                artifact_id=artifact_id,
                version=next_version,
                storage_ref=clean_ref,
                size_bytes=size_bytes,
                content_hash=content_hash,
            )
            logger.info(
                "Created revision v%d for artifact '%s' (ver_id: %s, %d bytes)",
                next_version,
                artifact_id,
                created_version.id,
                size_bytes,
            )
            return created_version

    def get_artifact_versions(self, artifact_id: str) -> List[ArtifactVersion]:
        """List all version snapshots for an artifact."""
        with get_connection(self.db_path) as conn:
            # Ensure artifact exists
            artifact = ArtifactRepository.get_artifact(conn, artifact_id)
            if not artifact:
                raise EntityNotFoundError("Artifact", artifact_id)
            return ArtifactRepository.get_artifact_versions(conn, artifact_id)

    def record_validation_result(
        self,
        artifact_id: str,
        is_valid: bool,
        score: float,
        hallucination_check_passed: bool = True,
        citations_verified: Optional[List[CitationVerification]] = None,
        warnings: Optional[List[str]] = None,
        errors: Optional[List[str]] = None,
    ) -> ValidationResult:
        """Record an automated validation report and update the artifact's validation status.

        Enforces standardized 0.0 - 1.0 confidence score (threshold >= 0.70).
        """
        if not (0.0 <= score <= 1.0):
            raise ValueError(f"Validation score must be between 0.0 and 1.0, got {score}")

        with get_connection(self.db_path) as conn:
            artifact = ArtifactRepository.get_artifact(conn, artifact_id)
            if not artifact:
                raise EntityNotFoundError("Artifact", artifact_id)

            result = ValidationResult(
                artifact_id=artifact_id,
                is_valid=is_valid,
                score=score,
                hallucination_check_passed=hallucination_check_passed,
                citations_verified=citations_verified or [],
                warnings=warnings or [],
                errors=errors or [],
            )
            saved_result = ArtifactRepository.create_validation_result(conn, result)

            # Synchronize artifact validation status
            new_status = ValidationStatus.VALID if is_valid else ValidationStatus.INVALID
            if not is_valid and warnings and not errors:
                new_status = ValidationStatus.WARNING
            ArtifactRepository.update_artifact_validation_status(conn, artifact_id, new_status)

            logger.info(
                "Recorded validation for artifact '%s': is_valid=%s, score=%.2f, status=%s",
                artifact_id,
                is_valid,
                score,
                new_status.value,
            )
            return saved_result

    def get_validation_result(self, artifact_id: str) -> Optional[ValidationResult]:
        """Retrieve the most recent validation report for an artifact."""
        with get_connection(self.db_path) as conn:
            artifact = ArtifactRepository.get_artifact(conn, artifact_id)
            if not artifact:
                raise EntityNotFoundError("Artifact", artifact_id)
            return ArtifactRepository.get_validation_result(conn, artifact_id)

    def record_provenance(
        self,
        artifact_id: str,
        source_hashes: List[str],
        generator_name: str,
        model_version: str,
        canonical_content_hash: Optional[str] = None,
        signature: Optional[str] = None,
        transformation_job_id: Optional[str] = None,
    ) -> ProvenanceRecord:
        """Record a cryptographic provenance ledger entry for an artifact."""
        if not source_hashes:
            raise ValueError("At least one input source hash is required for provenance")

        with get_connection(self.db_path) as conn:
            artifact = ArtifactRepository.get_artifact(conn, artifact_id)
            if not artifact:
                raise EntityNotFoundError("Artifact", artifact_id)

            record = ProvenanceRecord(
                artifact_id=artifact_id,
                artifact_hash=artifact.content_hash,
                source_hashes=source_hashes,
                canonical_content_hash=canonical_content_hash,
                transformation_job_id=transformation_job_id or artifact.job_id,
                generator_name=generator_name.strip(),
                model_version=model_version.strip(),
                signature=signature.strip() if signature else None,
            )
            saved = ArtifactRepository.create_provenance_record(conn, record)
            logger.info(
                "Recorded provenance ledger entry '%s' for artifact '%s' (generator: %s)",
                saved.id,
                artifact_id,
                generator_name,
            )
            return saved

    def get_provenance(self, artifact_id: str) -> Optional[ProvenanceRecord]:
        """Retrieve the cryptographic provenance record for an artifact."""
        with get_connection(self.db_path) as conn:
            artifact = ArtifactRepository.get_artifact(conn, artifact_id)
            if not artifact:
                raise EntityNotFoundError("Artifact", artifact_id)
            return ArtifactRepository.get_provenance_record(conn, artifact_id)


artifact_service = ArtifactService()
