"""Repository for Artifact, ArtifactVersion, ValidationResult, and ProvenanceRecord."""

from datetime import datetime
import json
from typing import Any, List, Optional
from ...models.artifact import Artifact, ArtifactVersion
from ...models.provenance import CitationVerification, ProvenanceRecord, ValidationResult
from ...models.enums import ArtifactType, ValidationStatus
from .common import parse_dt, parse_json


class ArtifactRepository:
    """CRUD repository for Artifacts, Versions, Validation Reports, and Provenance records."""

    @staticmethod
    def create_artifact(conn: Any, artifact: Artifact) -> Artifact:
        sql = """
            INSERT INTO artifacts (
                id, project_id, job_id, title, artifact_type, file_format,
                storage_ref, size_bytes, content_hash, description, stats,
                version, validation_status, created_at, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        conn.execute(sql, (
            artifact.id,
            artifact.project_id,
            artifact.job_id,
            artifact.title,
            artifact.artifact_type.value,
            artifact.file_format,
            artifact.storage_ref,
            artifact.size_bytes,
            artifact.content_hash,
            artifact.description,
            artifact.stats,
            artifact.version,
            artifact.validation_status.value,
            artifact.created_at.isoformat(),
            json.dumps(artifact.metadata),
        ))
        return artifact

    @staticmethod
    def _row_to_model(row: Any) -> Artifact:
        return Artifact(
            id=row["id"],
            project_id=row["project_id"],
            job_id=row["job_id"],
            title=row["title"],
            artifact_type=ArtifactType(row["artifact_type"]),
            file_format=row["file_format"],
            storage_ref=row["storage_ref"],
            size_bytes=row["size_bytes"],
            content_hash=row["content_hash"],
            description=row["description"],
            stats=row["stats"],
            version=row["version"],
            validation_status=ValidationStatus(row["validation_status"]),
            created_at=parse_dt(row["created_at"]),
            metadata=parse_json(row["metadata_json"], default={}),
        )

    @staticmethod
    def get_artifact(conn: Any, artifact_id: str) -> Optional[Artifact]:
        sql = """
            SELECT id, project_id, job_id, title, artifact_type, file_format,
                   storage_ref, size_bytes, content_hash, description, stats,
                   version, validation_status, created_at, metadata_json
            FROM artifacts
            WHERE id = ?
        """
        row = conn.execute(sql, (artifact_id,)).fetchone()
        if not row:
            return None
        return ArtifactRepository._row_to_model(row)

    @staticmethod
    def list_artifacts_by_project(conn: Any, project_id: str) -> List[Artifact]:
        sql = """
            SELECT id, project_id, job_id, title, artifact_type, file_format,
                   storage_ref, size_bytes, content_hash, description, stats,
                   version, validation_status, created_at, metadata_json
            FROM artifacts
            WHERE project_id = ?
            ORDER BY created_at DESC
        """
        rows = conn.execute(sql, (project_id,)).fetchall()
        return [ArtifactRepository._row_to_model(row) for row in rows]

    @staticmethod
    def list_artifacts_by_job(conn: Any, job_id: str) -> List[Artifact]:
        sql = """
            SELECT id, project_id, job_id, title, artifact_type, file_format,
                   storage_ref, size_bytes, content_hash, description, stats,
                   version, validation_status, created_at, metadata_json
            FROM artifacts
            WHERE job_id = ?
            ORDER BY created_at DESC
        """
        rows = conn.execute(sql, (job_id,)).fetchall()
        return [ArtifactRepository._row_to_model(row) for row in rows]

    @staticmethod
    def update_artifact_validation_status(
        conn: Any, artifact_id: str, status: ValidationStatus
    ) -> bool:
        sql = "UPDATE artifacts SET validation_status = ? WHERE id = ?"
        cur = conn.execute(sql, (status.value, artifact_id))
        return cur.rowcount > 0

    @staticmethod
    def update_artifact_metadata(
        conn: Any, artifact_id: str, metadata: dict
    ) -> bool:
        sql = "UPDATE artifacts SET metadata_json = ? WHERE id = ?"
        cur = conn.execute(sql, (json.dumps(metadata), artifact_id))
        return cur.rowcount > 0

    @staticmethod
    def create_artifact_version(conn: Any, version: ArtifactVersion) -> ArtifactVersion:
        sql = """
            INSERT INTO artifact_versions (
                id, artifact_id, version_number, storage_ref, size_bytes,
                content_hash, change_summary, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        conn.execute(sql, (
            version.id,
            version.artifact_id,
            version.version_number,
            version.storage_ref,
            version.size_bytes,
            version.content_hash,
            version.change_summary,
            version.created_at.isoformat(),
        ))
        return version

    @staticmethod
    def _row_to_version(row: Any) -> ArtifactVersion:
        return ArtifactVersion(
            id=row["id"],
            artifact_id=row["artifact_id"],
            version_number=row["version_number"],
            storage_ref=row["storage_ref"],
            size_bytes=row["size_bytes"],
            content_hash=row["content_hash"],
            change_summary=row["change_summary"],
            created_at=parse_dt(row["created_at"]),
        )

    @staticmethod
    def get_artifact_versions(conn: Any, artifact_id: str) -> List[ArtifactVersion]:
        sql = """
            SELECT id, artifact_id, version_number, storage_ref, size_bytes,
                   content_hash, change_summary, created_at
            FROM artifact_versions
            WHERE artifact_id = ?
            ORDER BY version_number ASC
        """
        rows = conn.execute(sql, (artifact_id,)).fetchall()
        return [ArtifactRepository._row_to_version(row) for row in rows]

    @staticmethod
    def create_validation_result(conn: Any, result: ValidationResult) -> ValidationResult:
        sql = """
            INSERT INTO validation_results (
                id, artifact_id, is_valid, score, hallucination_check_passed,
                citations_verified_json, warnings_json, errors_json, validated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        citations_data = [c.model_dump() for c in result.citations_verified]
        conn.execute(sql, (
            result.id,
            result.artifact_id,
            bool(result.is_valid),
            result.score,
            bool(result.hallucination_check_passed),
            json.dumps(citations_data),
            json.dumps(result.warnings),
            json.dumps(result.errors),
            result.validated_at.isoformat(),
        ))
        return result

    @staticmethod
    def get_validation_result(conn: Any, artifact_id: str) -> Optional[ValidationResult]:
        sql = """
            SELECT id, artifact_id, is_valid, score, hallucination_check_passed,
                   citations_verified_json, warnings_json, errors_json, validated_at
            FROM validation_results
            WHERE artifact_id = ?
            ORDER BY validated_at DESC
            LIMIT 1
        """
        row = conn.execute(sql, (artifact_id,)).fetchone()
        if not row:
            return None

        raw_citations = parse_json(row["citations_verified_json"], default=[])
        citations = [CitationVerification(**c) for c in raw_citations]

        return ValidationResult(
            id=row["id"],
            artifact_id=row["artifact_id"],
            is_valid=bool(row["is_valid"]),
            score=row["score"],
            hallucination_check_passed=bool(row["hallucination_check_passed"]),
            citations_verified=citations,
            warnings=parse_json(row["warnings_json"], default=[]),
            errors=parse_json(row["errors_json"], default=[]),
            validated_at=parse_dt(row["validated_at"]),
        )

    @staticmethod
    def create_provenance_record(conn: Any, provenance: ProvenanceRecord) -> ProvenanceRecord:
        sql = """
            INSERT INTO provenance (
                id, artifact_id, artifact_hash, source_hashes_json,
                canonical_content_hash, transformation_job_id,
                generator_name, model_version, signature, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        conn.execute(sql, (
            provenance.id,
            provenance.artifact_id,
            provenance.artifact_hash,
            json.dumps(provenance.source_hashes),
            provenance.canonical_content_hash,
            provenance.transformation_job_id,
            provenance.generator_name,
            provenance.model_version,
            provenance.signature,
            provenance.created_at.isoformat(),
        ))
        return provenance

    @staticmethod
    def get_provenance_record(conn: Any, artifact_id: str) -> Optional[ProvenanceRecord]:
        sql = """
            SELECT id, artifact_id, artifact_hash, source_hashes_json,
                   canonical_content_hash, transformation_job_id,
                   generator_name, model_version, signature, created_at
            FROM provenance
            WHERE artifact_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        """
        row = conn.execute(sql, (artifact_id,)).fetchone()
        if not row:
            return None

        return ProvenanceRecord(
            id=row["id"],
            artifact_id=row["artifact_id"],
            artifact_hash=row["artifact_hash"],
            source_hashes=parse_json(row["source_hashes_json"], default=[]),
            canonical_content_hash=row["canonical_content_hash"],
            transformation_job_id=row["transformation_job_id"],
            generator_name=row["generator_name"],
            model_version=row["model_version"],
            signature=row["signature"],
            created_at=parse_dt(row["created_at"]),
        )

    @staticmethod
    def list_artifacts(
        conn: Any,
        project_id: Optional[str] = None,
        job_id: Optional[str] = None,
        artifact_type: Optional[ArtifactType] = None,
    ) -> List[Artifact]:
        """List artifacts with optional filtering by project, job, or deliverable type."""
        query = """
            SELECT id, project_id, job_id, title, artifact_type, file_format,
                   storage_ref, size_bytes, content_hash, description, stats,
                   version, validation_status, created_at, metadata_json
            FROM artifacts
        """
        clauses = []
        params = []
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        if job_id:
            clauses.append("job_id = ?")
            params.append(job_id)
        if artifact_type:
            clauses.append("artifact_type = ?")
            params.append(artifact_type.value if hasattr(artifact_type, "value") else str(artifact_type))

        if clauses:
            query += " WHERE " + " AND ".join(clauses)

        query += " ORDER BY created_at DESC"
        rows = conn.execute(query, tuple(params)).fetchall()
        return [ArtifactRepository._row_to_model(row) for row in rows]

    @staticmethod
    def get_next_version_number(conn: Any, artifact_id: str) -> int:
        """Calculate next monotonic version using COALESCE(MAX(version_number), 0) + 1."""
        sql = "SELECT COALESCE(MAX(version_number), 0) + 1 FROM artifact_versions WHERE artifact_id = ?"
        row = conn.execute(sql, (artifact_id,)).fetchone()
        if not row:
            return 1
        val = next(iter(row.values())) if isinstance(row, dict) else row[0]
        return int(val) if val is not None else 1

    @staticmethod
    def update_artifact_version(
        conn: Any,
        artifact_id: str,
        version: int,
        storage_ref: str,
        size_bytes: int,
        content_hash: str,
    ) -> bool:
        """Update parent artifact current revision pointers."""
        sql = """
            UPDATE artifacts
            SET version = ?, storage_ref = ?, size_bytes = ?, content_hash = ?
            WHERE id = ?
        """
        cur = conn.execute(sql, (version, storage_ref, size_bytes, content_hash, artifact_id))
        return cur.rowcount > 0
