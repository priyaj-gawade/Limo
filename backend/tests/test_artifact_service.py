"""Unit tests for Phase D3.8: ArtifactService, file checks, versions, and provenance."""

from pathlib import Path
import pytest

from app.db.init import init_db
from app.exceptions import EntityNotFoundError, StorageError
from app.models.enums import ArtifactType, OutputFormat, ValidationStatus
from app.models.provenance import CitationVerification
from app.services.artifact_service import ArtifactService
from app.services.job_service import JobService
from app.services.project_service import ProjectService
from app.storage.service import StorageService


@pytest.fixture
def artifact_env(tmp_path: Path):
    """Isolated test environment for ArtifactService with sandboxed storage."""
    db_file = tmp_path / "artifact_test.db"
    storage_dir = tmp_path / "data"

    init_db(db_file)
    storage = StorageService(base_dir=storage_dir)
    storage.ensure_directories()

    proj_svc = ProjectService(db_path=str(db_file))
    job_svc = JobService(db_path=str(db_file))
    art_svc = ArtifactService(db_path=str(db_file), storage=storage)

    project = proj_svc.create_project(name="Deliverables Project")
    job = job_svc.create_job(
        requested_formats=[OutputFormat.PRESENTATION],
        project_id=project.id,
    )

    return {
        "db_file": db_file,
        "storage": storage,
        "proj_svc": proj_svc,
        "job_svc": job_svc,
        "art_svc": art_svc,
        "project": project,
        "job": job,
    }


def test_register_artifact_requires_physical_file(artifact_env) -> None:
    """Pre-condition: Refuse registration if referenced file does not physically exist."""
    art_svc: ArtifactService = artifact_env["art_svc"]
    project = artifact_env["project"]
    job = artifact_env["job"]

    with pytest.raises(StorageError, match="Referenced artifact file does not exist in storage"):
        art_svc.register_artifact(
            title="Non-existent Deck",
            artifact_type=ArtifactType.SLIDE,
            file_format=".pptx",
            storage_ref="artifacts/phantom_dir/missing.pptx",
            project_id=project.id,
            job_id=job.id,
        )


def test_register_artifact_computes_hash_and_size(artifact_env) -> None:
    """Verify registration computes SHA-256 and size directly from physical disk."""
    art_svc: ArtifactService = artifact_env["art_svc"]
    storage: StorageService = artifact_env["storage"]
    project = artifact_env["project"]
    job = artifact_env["job"]

    file_content = b"PK\x03\x04Real PowerPoint Presentation Binary Stream"
    ref, expected_size, expected_hash = storage.save_artifact_file(
        artifact_id="art_mock_1",
        filename="deck.pptx",
        content=file_content,
    )

    artifact = art_svc.register_artifact(
        title="Quarterly Strategy Deck",
        artifact_type=ArtifactType.SLIDE,
        file_format="pptx",  # Test normalization without leading dot
        storage_ref=ref,
        project_id=project.id,
        job_id=job.id,
        description="Executive slide deck",
        stats="12 Slides • 16:9",
    )

    assert artifact.id.startswith("art_")
    assert artifact.title == "Quarterly Strategy Deck"
    assert artifact.file_format == ".pptx"
    assert artifact.size_bytes == expected_size
    assert artifact.content_hash == expected_hash
    assert artifact.version == 1
    assert artifact.validation_status == ValidationStatus.PENDING

    # Test reading binary content
    downloaded = art_svc.read_artifact_content(artifact.id)
    assert downloaded == file_content


def test_artifact_version_increment(artifact_env) -> None:
    """Verify version snapshots use MAX(version_number) + 1 and update parent."""
    art_svc: ArtifactService = artifact_env["art_svc"]
    storage: StorageService = artifact_env["storage"]
    project = artifact_env["project"]

    # Initial deliverable (v1)
    v1_content = b"Draft report v1 content"
    ref1, _, hash1 = storage.save_artifact_file("art_report", "report.docx", v1_content)
    artifact = art_svc.register_artifact(
        title="Executive Report",
        artifact_type=ArtifactType.DOC,
        file_format=".docx",
        storage_ref=ref1,
        project_id=project.id,
    )
    assert artifact.version == 1

    # Revision (v2)
    v2_content = b"Updated executive report v2 with stakeholder feedback"
    ref2, size2, hash2 = storage.save_artifact_file("art_report", "report_v2.docx", v2_content)
    version = art_svc.create_artifact_version(
        artifact_id=artifact.id,
        storage_ref=ref2,
        change_summary="Incorporated stakeholder review comments",
    )

    assert version.id.startswith("ver_")
    assert version.artifact_id == artifact.id
    assert version.version_number == 2
    assert version.content_hash == hash2
    assert version.size_bytes == size2

    # Check parent artifact was updated
    updated_art = art_svc.get_artifact(artifact.id)
    assert updated_art.version == 2
    assert updated_art.storage_ref == ref2
    assert updated_art.content_hash == hash2

    # List versions (v1 initial + v2 revision)
    versions = art_svc.get_artifact_versions(artifact.id)
    assert len(versions) == 2
    assert versions[0].version_number == 1
    assert versions[1].version_number == 2



def test_record_validation_result(artifact_env) -> None:
    """Verify validation result recording synchronizes artifact validation status."""
    art_svc: ArtifactService = artifact_env["art_svc"]
    storage: StorageService = artifact_env["storage"]

    ref, _, _ = storage.save_artifact_file("art_brief", "brief.docx", b"Document content")
    artifact = art_svc.register_artifact(
        title="Policy Brief",
        artifact_type=ArtifactType.DOC,
        file_format=".docx",
        storage_ref=ref,
    )

    # 1. Record validation pass (score >= 0.70)
    citation = CitationVerification(
        claim="Market share expanded by 15%",
        source_id="src_data_1",
        source_hash="b" * 64,
        citation_text="Market share grew 15% in Q3",
        similarity_score=0.98,
    )
    val = art_svc.record_validation_result(
        artifact_id=artifact.id,
        is_valid=True,
        score=0.92,
        citations_verified=[citation],
    )
    assert val.is_valid is True
    assert val.score == 0.92

    # Check status updated
    updated = art_svc.get_artifact(artifact.id)
    assert updated.validation_status == ValidationStatus.VALID

    # 2. Guard: score must be between 0.0 and 1.0
    with pytest.raises(ValueError, match="Validation score must be between 0.0 and 1.0"):
        art_svc.record_validation_result(artifact.id, is_valid=False, score=1.5)


def test_record_provenance_record(artifact_env) -> None:
    """Verify cryptographic provenance ledger recording and retrieval."""
    art_svc: ArtifactService = artifact_env["art_svc"]
    storage: StorageService = artifact_env["storage"]
    job = artifact_env["job"]

    ref, _, _ = storage.save_artifact_file("art_prov", "slide.pptx", b"Presentation bytes")
    artifact = art_svc.register_artifact(
        title="Investor Presentation",
        artifact_type=ArtifactType.SLIDE,
        file_format=".pptx",
        storage_ref=ref,
        job_id=job.id,
    )

    source_hashes = ["c" * 64, "d" * 64]
    prov = art_svc.record_provenance(
        artifact_id=artifact.id,
        source_hashes=source_hashes,
        generator_name="GenOffice.SlideGenerator",
        model_version="v2.1.0",
        canonical_content_hash="e" * 64,
    )

    assert prov.id.startswith("prov_")
    assert prov.artifact_id == artifact.id
    assert prov.artifact_hash == artifact.content_hash
    assert prov.generator_name == "GenOffice.SlideGenerator"

    # Fetch provenance
    fetched = art_svc.get_provenance(artifact.id)
    assert fetched is not None
    assert fetched.id == prov.id
    assert fetched.source_hashes == source_hashes
