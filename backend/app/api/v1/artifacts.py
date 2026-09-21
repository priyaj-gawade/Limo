import inspect
import logging
import mimetypes
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Dict, Generator, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger("limo.api.artifacts")

from ...auth.config import auth_config
from ...auth.dependencies import authorize_resource, get_current_user
from ...exceptions import BadRequestError, EntityNotFoundError
from ...models.artifact import Artifact, ArtifactVersion
from ...models.enums import ArtifactType
from ...models.provenance import CitationVerification, ProvenanceRecord, ValidationResult
from ...models.user import User
from ...services.artifact_service import artifact_service
from ...services.job_service import job_service
from ...services.project_service import project_service

router = APIRouter(prefix="/artifacts", tags=["Artifacts"])


def _authorize_artifact(artifact: Artifact, current_user: User) -> None:
    """Check multi-tenant authorization for an artifact."""
    if auth_config.is_desktop_surface:
        return
    owner_id = artifact.metadata.get("user_id") if isinstance(artifact.metadata, dict) else None
    if not owner_id and artifact.project_id:
        try:
            proj = project_service.get_project(artifact.project_id)
            owner_id = proj.user_id
        except Exception:
            pass
    if not owner_id and artifact.job_id:
        try:
            job = job_service.get_job(artifact.job_id)
            owner_id = job.user_id
        except Exception:
            pass
    authorize_resource(owner_id, current_user)


def _iter_file_range(file_path: str, start: int, end: int, chunk_size: int = 64 * 1024) -> Generator[bytes, None, None]:
    """Yield file chunks within specified [start, end] byte range (inclusive)."""
    with open(file_path, "rb") as f:
        f.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            read_len = min(chunk_size, remaining)
            data = f.read(read_len)
            if not data:
                break
            remaining -= len(data)
            yield data


def _extract_video_poster(video_path: Path, duration: float = 3.0) -> Optional[bytes]:
    """Resilient multi-tier poster frame extraction via ffmpeg:
    1. Try t=0.5s.
    2. Fallback to min(0.1s, max(0.01s, duration - 0.05s)).
    3. Fallback to first frame (0.0s).
    """
    attempts = [
        ["-ss", "00:00:00.500"],
        ["-ss", f"{max(0.01, min(0.1, duration - 0.05)):.3f}"],
        [],  # frame 0 fallback
    ]

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        for ss_args in attempts:
            cmd = ["ffmpeg", "-y"] + ss_args + ["-i", str(video_path), "-frames:v", "1", "-q:v", "2", str(tmp_path)]
            try:
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if tmp_path.is_file() and tmp_path.stat().st_size > 0:
                    return tmp_path.read_bytes()
            except Exception:
                continue
    finally:
        if tmp_path.is_file():
            try:
                tmp_path.unlink()
            except Exception:
                pass
    return None


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
async def register_artifact(
    req: RegisterArtifactRequest,
    current_user: User = Depends(get_current_user),
) -> Artifact:
    """Register a generated deliverable. Rejects registration if referenced file does not exist."""
    if req.project_id:
        proj = project_service.get_project(req.project_id)
        authorize_resource(proj.user_id, current_user)
    if req.job_id:
        job = job_service.get_job(req.job_id)
        authorize_resource(job.user_id, current_user)

    metadata = dict(req.metadata)
    metadata["user_id"] = current_user.id

    return artifact_service.register_artifact(
        title=req.title,
        artifact_type=req.artifact_type,
        file_format=req.file_format,
        storage_ref=req.storage_ref,
        project_id=req.project_id,
        job_id=req.job_id,
        description=req.description,
        stats=req.stats,
        metadata=metadata,
    )


@router.get("", response_model=List[Artifact])
async def list_artifacts(
    project_id: Optional[str] = Query(None, description="Filter deliverables by project"),
    job_id: Optional[str] = Query(None, description="Filter deliverables by generating job"),
    artifact_type: Optional[ArtifactType] = Query(None, description="Filter deliverables by category"),
    current_user: User = Depends(get_current_user),
) -> List[Artifact]:
    """List deliverables with optional filtering, ordered by created_at DESC."""
    if project_id:
        proj = project_service.get_project(project_id)
        authorize_resource(proj.user_id, current_user)
    if job_id:
        job = job_service.get_job(job_id)
        authorize_resource(job.user_id, current_user)

    artifacts = artifact_service.list_artifacts(
        project_id=project_id,
        job_id=job_id,
        artifact_type=artifact_type,
    )

    if auth_config.is_web_surface:
        user_projects = {p.id for p in project_service.list_projects(user_id=current_user.id)}
        artifacts = [
            a for a in artifacts
            if a.metadata.get("user_id") == current_user.id or (a.project_id and a.project_id in user_projects)
        ]

    return artifacts


@router.get("/{artifact_id}", response_model=Artifact)
async def get_artifact(
    artifact_id: str,
    current_user: User = Depends(get_current_user),
) -> Artifact:
    """Retrieve metadata, version, and status for a deliverable artifact."""
    artifact = artifact_service.get_artifact(artifact_id)
    _authorize_artifact(artifact, current_user)
    return artifact


@router.get("/{artifact_id}/download")
async def download_artifact(
    artifact_id: str,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Download verified raw deliverable binary with cryptographic SHA-256 verification."""
    artifact = artifact_service.get_artifact(artifact_id)
    _authorize_artifact(artifact, current_user)
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


@router.get("/{artifact_id}/preview")
async def preview_artifact(
    artifact_id: str,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Preview deliverable content inline with resource authorization."""
    artifact = artifact_service.get_artifact(artifact_id)
    _authorize_artifact(artifact, current_user)
    content = artifact_service.read_artifact_content(artifact_id)

    media_type, _ = mimetypes.guess_type(f"artifact{artifact.file_format}")
    if not media_type:
        media_type = "text/plain"

    filename = f"{artifact.title.replace(' ', '_')}{artifact.file_format}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/{artifact_id}/stream")
async def stream_artifact(
    artifact_id: str,
    range_header: Optional[str] = Header(None, alias="Range"),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Stream deliverable with HTTP 206 Partial Content Range support for smooth seeking."""
    artifact = artifact_service.get_artifact(artifact_id)
    _authorize_artifact(artifact, current_user)

    from ...storage.boundary import is_worker_artifact_ref, parse_worker_artifact_id
    import httpx

    # 1. Heavy worker deliverable via Cloudflare Named Tunnel
    if is_worker_artifact_ref(artifact.storage_ref):
        worker_art_id = parse_worker_artifact_id(artifact.storage_ref)
        worker_base = os.getenv("TURBO_WORKER_URL") or "http://localhost:8005"
        worker_token = os.getenv("WORKER_AUTH_TOKEN") or "limo-turbo-worker-secret-key-12345"

        worker_url = f"{worker_base.rstrip('/')}/artifacts/{worker_art_id}"
        req_headers = {"X-Limo-Worker-Key": worker_token}
        if range_header:
            req_headers["range"] = range_header

        client = httpx.AsyncClient(timeout=30.0)
        try:
            req = client.build_request("GET", worker_url, headers=req_headers)
            r = await client.send(req, stream=True)

            if r.status_code not in (200, 206):
                await r.aclose()
                await client.aclose()
                raise HTTPException(
                    status_code=r.status_code,
                    detail="Failed to stream artifact from worker",
                )

            async def stream_content():
                try:
                    async for chunk in r.aiter_bytes(chunk_size=64 * 1024):
                        yield chunk
                finally:
                    await r.aclose()
                    await client.aclose()

            resp_headers = {}
            for h in ("content-range", "accept-ranges", "content-length", "content-type"):
                if h in r.headers:
                    resp_headers[h] = r.headers[h]

            return StreamingResponse(
                stream_content(),
                status_code=r.status_code,
                headers=resp_headers,
            )
        except httpx.RequestError as exc:
            await client.aclose()
            logger.error("Turbo Worker stream connection error: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Turbo Worker is offline or unreachable",
            )

    # 2. Local desktop artifact fallback
    try:
        file_path = artifact_service.storage.safe_resolve(artifact.storage_ref)
    except Exception:
        raise EntityNotFoundError("Artifact file", artifact_id)

    if not file_path.is_file():
        raise EntityNotFoundError("Artifact file", artifact_id)

    file_size = file_path.stat().st_size
    media_type, _ = mimetypes.guess_type(file_path.name)
    if not media_type:
        media_type = "video/mp4" if artifact.artifact_type == ArtifactType.VIDEO else "application/octet-stream"

    filename = f"{artifact.title.replace(' ', '_')}{artifact.file_format}"

    if range_header:
        # Match "bytes=start-end" or "bytes=start-" or "bytes=-suffix"
        range_match = re.match(r"^bytes=(\d*)-(\d*)$", range_header.strip())
        if range_match:
            start_str, end_str = range_match.groups()
            if start_str and end_str:
                start = int(start_str)
                end = int(end_str)
            elif start_str:
                start = int(start_str)
                end = file_size - 1
            elif end_str:
                start = max(0, file_size - int(end_str))
                end = file_size - 1
            else:
                start = 0
                end = file_size - 1

            if start >= file_size or end < start:
                return Response(
                    status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                    headers={"Content-Range": f"bytes */{file_size}"},
                )

            end = min(end, file_size - 1)
            content_length = end - start + 1
            headers = {
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
                "Content-Disposition": f'inline; filename="{filename}"',
            }
            return StreamingResponse(
                _iter_file_range(str(file_path), start, end),
                status_code=status.HTTP_206_PARTIAL_CONTENT,
                media_type=media_type,
                headers=headers,
            )

    # If no valid Range header, return 200 with Accept-Ranges
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(file_size),
        "Content-Disposition": f'inline; filename="{filename}"',
    }
    return StreamingResponse(
        _iter_file_range(str(file_path), 0, file_size - 1),
        status_code=status.HTTP_200_OK,
        media_type=media_type,
        headers=headers,
    )


@router.get("/{artifact_id}/thumbnail")
async def get_artifact_thumbnail(
    artifact_id: str,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Stream rendered page thumbnail for an artifact."""
    artifact = artifact_service.get_artifact(artifact_id)
    _authorize_artifact(artifact, current_user)
    thumb_ref = artifact.metadata.get("thumbnail_storage_ref") or f"artifacts/{artifact_id}/thumbnail.png"
    if artifact_service.storage.file_exists(thumb_ref):
        thumb_bytes = artifact_service.storage.read_file(thumb_ref)
        return Response(
            content=thumb_bytes,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=3600"},
        )

    # For video artifacts, if thumbnail is missing, dynamically extract and save it
    if artifact.artifact_type == ArtifactType.VIDEO:
        try:
            video_path = artifact_service.storage.safe_resolve(artifact.storage_ref)
            if video_path.is_file():
                duration = float(artifact.metadata.get("duration", 3.0))
                extracted_bytes = _extract_video_poster(video_path, duration=duration)
                if extracted_bytes:
                    saved_ref = artifact_service.storage.save_bytes(extracted_bytes, f"artifacts/{artifact_id}/thumbnail.png")
                    artifact_service.update_artifact_metadata(artifact_id, {"thumbnail_storage_ref": saved_ref})
                    return Response(
                        content=extracted_bytes,
                        media_type="image/png",
                        headers={"Cache-Control": "public, max-age=3600"},
                    )
        except Exception:
            pass

    raise EntityNotFoundError("Thumbnail", artifact_id)


@router.post("/{artifact_id}/open")
async def open_artifact_in_workspace(
    artifact_id: str,
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Open the artifact directly in GenOffice workspace."""
    from ...services.transformation.genoffice_client import genoffice_client

    artifact = artifact_service.get_artifact(artifact_id)
    _authorize_artifact(artifact, current_user)
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
async def create_artifact_version(
    artifact_id: str,
    req: CreateVersionRequest,
    current_user: User = Depends(get_current_user),
) -> ArtifactVersion:
    """Create a new historical revision snapshot for an artifact."""
    artifact = artifact_service.get_artifact(artifact_id)
    _authorize_artifact(artifact, current_user)
    return artifact_service.create_artifact_version(
        artifact_id=artifact_id,
        storage_ref=req.storage_ref,
        change_summary=req.change_summary,
    )


@router.get("/{artifact_id}/versions", response_model=List[ArtifactVersion])
async def list_artifact_versions(
    artifact_id: str,
    current_user: User = Depends(get_current_user),
) -> List[ArtifactVersion]:
    """List historical revision snapshots for an artifact."""
    artifact = artifact_service.get_artifact(artifact_id)
    _authorize_artifact(artifact, current_user)
    return artifact_service.get_artifact_versions(artifact_id)


@router.post("/{artifact_id}/validation", response_model=ValidationResult, status_code=status.HTTP_201_CREATED)
async def record_validation(
    artifact_id: str,
    req: RecordValidationRequest,
    current_user: User = Depends(get_current_user),
) -> ValidationResult:
    """Record an automated validation and citation verification report."""
    artifact = artifact_service.get_artifact(artifact_id)
    _authorize_artifact(artifact, current_user)
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
async def get_validation(
    artifact_id: str,
    current_user: User = Depends(get_current_user),
) -> Optional[ValidationResult]:
    """Get the latest verification report for an artifact."""
    artifact = artifact_service.get_artifact(artifact_id)
    _authorize_artifact(artifact, current_user)
    return artifact_service.get_validation_result(artifact_id)


@router.post("/{artifact_id}/provenance", response_model=ProvenanceRecord, status_code=status.HTTP_201_CREATED)
async def record_provenance(
    artifact_id: str,
    req: RecordProvenanceRequest,
    current_user: User = Depends(get_current_user),
) -> ProvenanceRecord:
    """Record a cryptographic provenance ledger entry for an artifact."""
    artifact = artifact_service.get_artifact(artifact_id)
    _authorize_artifact(artifact, current_user)
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
async def get_provenance(
    artifact_id: str,
    current_user: User = Depends(get_current_user),
) -> Optional[ProvenanceRecord]:
    """Get the cryptographic provenance record for an artifact."""
    artifact = artifact_service.get_artifact(artifact_id)
    _authorize_artifact(artifact, current_user)
    return artifact_service.get_provenance(artifact_id)


