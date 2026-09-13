"""Sources REST API router."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status
from pydantic import BaseModel, Field

from ...exceptions import EntityNotFoundError
from ...models.content import CanonicalContent
from ...models.enums import SourceType
from ...models.project import Source
from ...services.canonical.service import canonical_service
from ...services.extraction.models import ExtractedDocument, ExtractionSummaryResponse
from ...services.extraction.service import extraction_service
from ...services.normalization.service import normalization_service
from ...services.retrieval.models import RetrievalResult
from ...services.retrieval.service import retrieval_service
from ...services.source_service import source_service

router = APIRouter(prefix="/sources", tags=["Sources"])


class CreateTextSourceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255, description="Document title")
    text: str = Field(min_length=1, description="Raw textual content")
    project_id: Optional[str] = Field(default=None, description="Associated project ID")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CreateUrlSourceRequest(BaseModel):
    url: str = Field(min_length=1, description="Target HTTP/HTTPS URL")
    project_id: Optional[str] = Field(default=None, description="Associated project ID")
    metadata: Dict[str, Any] = Field(default_factory=dict)


@router.post("/upload", response_model=Source, status_code=status.HTTP_201_CREATED)
async def upload_source_file(
    file: UploadFile = File(...),
    project_id: Optional[str] = Form(None),
) -> Source:
    """Upload and register a raw file source with verified atomic storage."""
    content = await file.read()
    filename = file.filename or "uploaded_file"
    mime_type = file.content_type or "application/octet-stream"

    return source_service.register_file_source(
        filename=filename,
        content=content,
        mime_type=mime_type,
        project_id=project_id,
    )


@router.post("/text", response_model=Source, status_code=status.HTTP_201_CREATED)
async def create_text_source(req: CreateTextSourceRequest) -> Source:
    """Register a textual snippet source."""
    return source_service.register_text_source(
        name=req.name,
        text_content=req.text,
        project_id=req.project_id,
        metadata=req.metadata,
    )


@router.post("/url", response_model=Source, status_code=status.HTTP_201_CREATED)
async def create_url_source(req: CreateUrlSourceRequest) -> Source:
    """Fetch a remote web URL with verified SSRF protection and register as a source."""
    return await source_service.register_url_source(
        url=req.url,
        project_id=req.project_id,
        metadata=req.metadata,
    )


@router.post("/{source_id}/extract", response_model=ExtractionSummaryResponse)
async def extract_source_content(source_id: str) -> ExtractionSummaryResponse:
    """Execute extraction pipeline on source content and return lightweight status summary."""
    source = source_service.get_source(source_id)
    doc = await extraction_service.extract_source(source)
    return extraction_service.build_summary_response(doc)


@router.get("/{source_id}/extracted", response_model=ExtractedDocument)
async def get_extracted_content(source_id: str) -> ExtractedDocument:
    """Retrieve full structured ExtractedDocument for a source."""
    source = source_service.get_source(source_id)
    doc = extraction_service.get_cached_extraction(source_id)
    if not doc:
        doc = await extraction_service.extract_source(source)
    return doc


@router.post("/{source_id}/canonicalize", response_model=CanonicalContent)
async def canonicalize_source_content(source_id: str) -> CanonicalContent:
    """Execute normalization and canonicalization pipeline on already-extracted evidence."""
    source = source_service.get_source(source_id)
    doc = extraction_service.get_cached_extraction(source_id)
    if not doc:
        doc = await extraction_service.extract_source(source)
    norm_doc = normalization_service.normalize_extracted_document(doc)
    return await canonical_service.canonicalize(norm_doc)


@router.get("/{source_id}/canonical", response_model=CanonicalContent)
async def get_canonical_content(source_id: str) -> CanonicalContent:
    """Retrieve persisted CanonicalContent representation for a source."""
    source_service.get_source(source_id)  # Validate source exists
    canonical = canonical_service.get_canonical_by_source_id(source_id)
    if not canonical:
        raise EntityNotFoundError("CanonicalContent", source_id)
    return canonical


@router.get("", response_model=List[Source])
async def list_sources(project_id: str = Query(..., description="Project ID to filter sources by")) -> List[Source]:
    """List all sources associated with a project."""
    return source_service.list_sources(project_id=project_id)


@router.get("/{source_id}", response_model=Source)
async def get_source(source_id: str) -> Source:
    """Get metadata for a specific source asset."""
    return source_service.get_source(source_id)


@router.get("/{source_id}/download")
async def download_source(source_id: str) -> Response:
    """Download raw binary contents of a source asset with cryptographic verification."""
    source = source_service.get_source(source_id)
    content = source_service.read_source_content(source_id)

    return Response(
        content=content,
        media_type=source.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{source.name}"'},
    )


class RetrieveContextRequest(BaseModel):
    query: str = Field(min_length=1, description="Search query string")
    max_tokens: Optional[int] = Field(default=None, description="Max token budget for retrieved context")
    top_k: int = Field(default=10, ge=1, le=50, description="Max candidate chunks")


@router.post("/{source_id}/retrieve", response_model=RetrievalResult)
async def retrieve_source_context(source_id: str, request: RetrieveContextRequest) -> RetrievalResult:
    """Retrieve grounded, section-aware context chunks from an ingested source within a token budget."""
    source_service.get_source(source_id)  # Validate source exists
    return await retrieval_service.retrieve_context(
        query=request.query,
        source_id=source_id,
        max_tokens=request.max_tokens,
        top_k=request.top_k,
    )


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(source_id: str) -> None:
    """Delete a source asset from storage and database."""
    source_service.delete_source(source_id)

