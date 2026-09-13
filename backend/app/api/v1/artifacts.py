"""Artifacts REST API router."""

import inspect
import mimetypes
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query, Response, status
from pydantic import BaseModel, Field

from ...exceptions import BadRequestError, EntityNotFoundError
from ...models.artifact import Artifact, ArtifactVersion
from ...models.enums import ArtifactType
from ...models.provenance import CitationVerification, ProvenanceRecord, ValidationResult
from ...services.artifact_service import artifact_service

router = APIRouter(prefix="/artifacts", tags=["Artifacts"])


class RegisterArtifactRequest(BaseModel):
    """Payload for registering a deliverable artifact."""
    title: str = Field(min_length=1, max_length=255, description="Deliverable title")
    artifact_type: ArtifactType = Field(description="Deliverable category")
    file_format: str = Field(min_length=1, max_length=16, description="File extension e.g. '.docx', '.pptx'")
    storage_ref: str = Field(min_length=1, description="Internal storage reference key")
    project_id: Optional[str] = Field(default=None, description="Associated project ID")
    job_id: Optional[str] = Field(default=None, description="Generating TransformationJob ID")
    description: Optional[str] = Field(default=None, description="Brief summary of deliverable contents")
    stats: Optional[str] = Field(default=None, description="Display stats (e.g. '10 Slides • 16:9 • PPTX')")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary generator/format metadata")


class CreateVersionRequest(BaseModel):
    """Payload for registering a revision snapshot."""
    storage_ref: str = Field(min_length=1, description="Internal storage key for this revision")
    change_summary: Optional[str] = Field(default=None, description="Changelog or reason for revision")


class RecordValidationRequest(BaseModel):
    """Payload for recording an automated verification report."""
    is_valid: bool = Field(description="Whether quality and grounding passed")
    score: float = Field(ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0 (>=0.70 pass)")
    hallucination_check_passed: bool = Field(default=True, description="True if zero unsupported claims")
    citations_verified: List[CitationVerification] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class RecordProvenanceRequest(BaseModel):
    """Payload for recording a cryptographic provenance audit record."""
    source_hashes: List[str] = Field(min_length=1, description="SHA-256 hashes of input sources")
    generator_name: str = Field(min_length=1, description="Generator engine or pipeline identifier")
    model_version: str = Field(min_length=1, description="Model or engine version")
    canonical_content_hash: Optional[str] = Field(default=None, description="Intermediate canonical SHA-256 hash")
    signature: Optional[str] = Field(default=None, description="Cryptographic signature")
    transformation_job_id: Optional[str] = Field(default=None, description="Generating TransformationJob ID")


@router.post("", response_model=Artifact, status_code=status.HTTP_201_CREATED)
async def register_artifact(req: RegisterArtifactRequest) -> Artifact:
    """Register a generated deliverable. Rejects registration if referenced file does not exist."""
    return artifact_service.register_artifact(
        title=req.title,
        artifact_type=req.artifact_type,
        file_format=req.file_format,
        storage_ref=req.storage_ref,
        project_id=req.project_id,
        job_id=req.job_id,
        description=req.description,
        stats=req.stats,
        metadata=req.metadata,
    )


@router.get("", response_model=List[Artifact])
async def list_artifacts(
    project_id: Optional[str] = Query(None, description="Filter deliverables by project"),
    job_id: Optional[str] = Query(None, description="Filter deliverables by generating job"),
    artifact_type: Optional[ArtifactType] = Query(None, description="Filter deliverables by category"),
) -> List[Artifact]:
    """List deliverables with optional filtering, ordered by created_at DESC."""
    return artifact_service.list_artifacts(
        project_id=project_id,
        job_id=job_id,
        artifact_type=artifact_type,
    )


@router.get("/{artifact_id}", response_model=Artifact)
async def get_artifact(artifact_id: str) -> Artifact:
    """Retrieve metadata, version, and status for a deliverable artifact."""
    return artifact_service.get_artifact(artifact_id)


@router.get("/{artifact_id}/download")
async def download_artifact(artifact_id: str) -> Response:
    """Download verified raw deliverable binary with cryptographic SHA-256 verification."""
    artifact = artifact_service.get_artifact(artifact_id)
    content = artifact_service.read_artifact_content(artifact_id)

    # Determine appropriate MIME media type
    media_type, _ = mimetypes.guess_type(f"artifact{artifact.file_format}")
    if not media_type:
        media_type = "application/octet-stream"

    filename = f"{artifact.title.replace(' ', '_')}{artifact.file_format}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{artifact_id}/thumbnail")
async def get_artifact_thumbnail(artifact_id: str) -> Response:
    """Stream rendered page thumbnail for an artifact."""
    artifact = artifact_service.get_artifact(artifact_id)
    thumb_ref = artifact.metadata.get("thumbnail_storage_ref") or f"artifacts/{artifact_id}/thumbnail.png"
    if not artifact_service.storage.file_exists(thumb_ref):
        raise EntityNotFoundError("Thumbnail", artifact_id)

    thumb_bytes = artifact_service.storage.read_file(thumb_ref)
    return Response(
        content=thumb_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.post("/{artifact_id}/open")
async def open_artifact_in_workspace(artifact_id: str) -> Dict[str, Any]:
    """Open the artifact directly in GenOffice workspace."""
    from ...services.transformation.genoffice_client import genoffice_client

    artifact = artifact_service.get_artifact(artifact_id)
    genoffice_path = artifact.metadata.get("genoffice_file_path")
    if not genoffice_path:
        # Fallback to physical sandboxed path if absolute genoffice_file_path is missing
        try:
            resolved_path = str(artifact_service.storage.safe_resolve(artifact.storage_ref))
            genoffice_path = resolved_path
        except Exception:
            raise BadRequestError(f"Artifact '{artifact_id}' does not have an openable file path")

    open_res = genoffice_client.open_file(genoffice_path)
    if inspect.isawaitable(open_res):
        result = await open_res
    else:
        result = open_res

    return {
        "status": "opened",
        "artifact_id": artifact_id,
        "file_path": genoffice_path,
        "details": result,
    }


@router.post("/{artifact_id}/versions", response_model=ArtifactVersion, status_code=status.HTTP_201_CREATED)
async def create_artifact_version(artifact_id: str, req: CreateVersionRequest) -> ArtifactVersion:
    """Create a new historical revision snapshot for an artifact."""
    return artifact_service.create_artifact_version(
        artifact_id=artifact_id,
        storage_ref=req.storage_ref,
        change_summary=req.change_summary,
    )


@router.get("/{artifact_id}/versions", response_model=List[ArtifactVersion])
async def list_artifact_versions(artifact_id: str) -> List[ArtifactVersion]:
    """List historical revision snapshots for an artifact."""
    return artifact_service.get_artifact_versions(artifact_id)


@router.post("/{artifact_id}/validation", response_model=ValidationResult, status_code=status.HTTP_201_CREATED)
async def record_validation(artifact_id: str, req: RecordValidationRequest) -> ValidationResult:
    """Record an automated validation and citation verification report."""
    return artifact_service.record_validation_result(
        artifact_id=artifact_id,
        is_valid=req.is_valid,
        score=req.score,
        hallucination_check_passed=req.hallucination_check_passed,
        citations_verified=req.citations_verified,
        warnings=req.warnings,
        errors=req.errors,
    )


@router.get("/{artifact_id}/validation", response_model=Optional[ValidationResult])
async def get_validation(artifact_id: str) -> Optional[ValidationResult]:
    """Get the latest verification report for an artifact."""
    return artifact_service.get_validation_result(artifact_id)


@router.post("/{artifact_id}/provenance", response_model=ProvenanceRecord, status_code=status.HTTP_201_CREATED)
async def record_provenance(artifact_id: str, req: RecordProvenanceRequest) -> ProvenanceRecord:
    """Record a cryptographic provenance ledger entry for an artifact."""
    return artifact_service.record_provenance(
        artifact_id=artifact_id,
        source_hashes=req.source_hashes,
        generator_name=req.generator_name,
        model_version=req.model_version,
        canonical_content_hash=req.canonical_content_hash,
        signature=req.signature,
        transformation_job_id=req.transformation_job_id,
    )


@router.get("/{artifact_id}/provenance", response_model=Optional[ProvenanceRecord])
async def get_provenance(artifact_id: str) -> Optional[ProvenanceRecord]:
    """Get the cryptographic provenance record for an artifact."""
    return artifact_service.get_provenance(artifact_id)
