"""Tests for Phase D3.3: SQLite Storage Layer."""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import pytest

from app.db.connection import get_connection
from app.db.init import init_db
from app.db.repositories import (
    ArtifactRepository,
    ChatRepository,
    JobRepository,
    ProjectRepository,
    SourceRepository,
)
from app.models.enums import (
    ArtifactType,
    CommunicationObjective,
    ContentStyle,
    DetailLevel,
    FeatureMode,
    JobState,
    MessageRole,
    OutputFormat,
    SourceType,
    ValidationStatus,
)
from app.models.project import Project, Source
from app.models.chat import ChatSession, Message, MessageAttachment
from app.models.job import GenerationConfig, TransformationJob
from app.models.content import (
    CanonicalClaim,
    CanonicalContent,
    CanonicalDataPoint,
    CanonicalEntity,
    CanonicalEvent,
    CanonicalFact,
    CanonicalIntent,
    CanonicalReference,
)
from app.models.artifact import Artifact, ArtifactVersion
from app.models.provenance import CitationVerification, ProvenanceRecord, ValidationResult


@pytest.fixture
def test_db_path(tmp_path: Path) -> Path:
    """Initialize an isolated test database in a temporary directory."""
    db_file = tmp_path / "test_limo.db"
    init_db(db_file)
    return db_file


def test_schema_initialization_is_idempotent(test_db_path: Path) -> None:
    """Verify running init_db multiple times succeeds without schema collisions."""
    init_db(test_db_path)
    init_db(test_db_path)

    with get_connection(test_db_path) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = [r["name"] for r in tables]
        expected_tables = [
            "artifact_versions",
            "artifacts",
            "canonical_contents",
            "chats",
            "jobs",
            "messages",
            "projects",
            "provenance",
            "sources",
            "validation_results",
        ]
        for tbl in expected_tables:
            assert tbl in table_names


def test_transaction_rollback_on_exception(test_db_path: Path) -> None:
    """Verify that exceptions inside get_connection rollback the transaction."""
    project = Project(name="Rollback Test Project")

    with pytest.raises(RuntimeError):
        with get_connection(test_db_path) as conn:
            ProjectRepository.create_project(conn, project)
            raise RuntimeError("Simulated crash mid-transaction")

    # Verify project was not committed
    with get_connection(test_db_path) as conn:
        assert ProjectRepository.get_project(conn, project.id) is None


def test_project_and_source_crud(test_db_path: Path) -> None:
    """Verify Project and Source CRUD operations."""
    with get_connection(test_db_path) as conn:
        # Create Project
        project = Project(
            name="Quarterly Threat Assessment",
            description="Analysis of APT telemetry",
            metadata={"priority": "high"},
        )
        created_proj = ProjectRepository.create_project(conn, project)
        assert created_proj.id == project.id

        # Read Project
        fetched_proj = ProjectRepository.get_project(conn, project.id)
        assert fetched_proj is not None
        assert fetched_proj.name == "Quarterly Threat Assessment"
        assert fetched_proj.metadata["priority"] == "high"

        # Update Project
        fetched_proj.name = "Updated Threat Assessment"
        updated_proj = ProjectRepository.update_project(conn, fetched_proj)
        assert updated_proj is not None
        assert updated_proj.name == "Updated Threat Assessment"

        # Create Source linked to Project
        source = Source(
            project_id=project.id,
            name="telemetry_logs.csv",
            source_type=SourceType.TABULAR,
            mime_type="text/csv",
            storage_ref="sources/src_1/telemetry_logs.csv",
            size_bytes=1024,
            content_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            extracted_text="header1,header2\nval1,val2",
        )
        SourceRepository.create_source(conn, source)

        # Retrieve Source
        fetched_source = SourceRepository.get_source(conn, source.id)
        assert fetched_source is not None
        assert fetched_source.project_id == project.id
        assert fetched_source.extracted_text == "header1,header2\nval1,val2"

        # List Sources by Project
        sources_list = SourceRepository.list_sources_by_project(conn, project.id)
        assert len(sources_list) == 1
        assert sources_list[0].id == source.id


def test_chat_session_and_message_cascade_delete(test_db_path: Path) -> None:
    """Verify chat session management and cascade deletion of messages."""
    with get_connection(test_db_path) as conn:
        session = ChatSession(title="Executive Briefing Thread", mode=FeatureMode.DOCS)
        ChatRepository.create_session(conn, session)

        # Add message with attachment
        msg = Message(
            session_id=session.id,
            role=MessageRole.USER,
            content="Generate executive briefing document from telemetry.",
            mode=FeatureMode.DOCS,
            attachments=[
                MessageAttachment(
                    id="att_1",
                    name="data.json",
                    size_bytes=512,
                    mime_type="application/json",
                )
            ],
            execution_summary="Ingested 1 attachment",
        )
        ChatRepository.add_message(conn, msg)

        # Retrieve messages
        msgs = ChatRepository.get_messages(conn, session.id)
        assert len(msgs) == 1
        assert msgs[0].id == msg.id
        assert len(msgs[0].attachments) == 1
        assert msgs[0].attachments[0].name == "data.json"

        # Delete session -> messages must be deleted via foreign key CASCADE
        deleted = ChatRepository.delete_session(conn, session.id)
        assert deleted is True

        # Verify messages table is empty for this session
        orphans = ChatRepository.get_messages(conn, session.id)
        assert len(orphans) == 0


def test_job_and_canonical_content_repository(test_db_path: Path) -> None:
    """Verify TransformationJob and CanonicalContent persistence."""
    with get_connection(test_db_path) as conn:
        job = TransformationJob(
            requested_formats=[OutputFormat.SUMMARY, OutputFormat.PRESENTATION],
            configuration=GenerationConfig(
                audience="C-Suite",
                tone="Authoritative",
                detail_level=DetailLevel.ANALYTICAL,
                objective=CommunicationObjective.ALERT,
                style=ContentStyle.CORPORATE,
            ),
        )
        JobRepository.create_job(conn, job)

        fetched_job = JobRepository.get_job(conn, job.id)
        assert fetched_job is not None
        assert fetched_job.state == JobState.QUEUED
        assert OutputFormat.PRESENTATION in fetched_job.requested_formats
        assert fetched_job.configuration.audience == "C-Suite"

        # Update progress
        JobRepository.update_job_progress(
            conn,
            job_id=job.id,
            state=JobState.PROCESSING,
            progress=0.45,
            current_stage="Synthesizing Canonical Content",
        )
        updated_job = JobRepository.get_job(conn, job.id)
        assert updated_job is not None
        assert updated_job.state == JobState.PROCESSING
        assert updated_job.progress == 0.45
        assert updated_job.current_stage == "Synthesizing Canonical Content"

        # CanonicalContent persistence
        canonical = CanonicalContent(
            source_ids=["src_100"],
            title="Strategic Threat Synthesis",
            context="Telemetry indicates active beaconing.",
            intent=CanonicalIntent(
                primary_purpose="Brief leadership",
                core_narrative="Mitigation required immediately",
            ),
            entities=[
                CanonicalEntity(name="C2 Server", category="Infrastructure", relevance_score=0.9)
            ],
            facts=[
                CanonicalFact(statement="Beacon detected at 03:00Z", confidence=0.99)
            ],
            claims=[
                CanonicalClaim(claim="Actor is APT29", evidence="Signature match")
            ],
            events=[
                CanonicalEvent(title="Initial Compromise", timestamp_desc="T-24h")
            ],
            data_points=[
                CanonicalDataPoint(metric="Compromised Hosts", value="14")
            ],
            recommendations=["Isolate VLAN 4"],
            references=[
                CanonicalReference(citation_key="[REF-1]", title="Firewall Log")
            ],
            content_hash="a" * 64,
        )
        JobRepository.save_canonical_content(conn, canonical)

        fetched_can = JobRepository.get_canonical_content(conn, canonical.id)
        assert fetched_can is not None
        assert fetched_can.title == "Strategic Threat Synthesis"
        assert len(fetched_can.entities) == 1
        assert fetched_can.entities[0].name == "C2 Server"
        assert len(fetched_can.facts) == 1
        assert fetched_can.facts[0].statement == "Beacon detected at 03:00Z"


def test_artifact_versions_uniqueness_constraint(test_db_path: Path) -> None:
    """Verify that UNIQUE(artifact_id, version_number) prevents duplicate version entries."""
    with get_connection(test_db_path) as conn:
        artifact = Artifact(
            title="Executive Report",
            artifact_type=ArtifactType.DOC,
            file_format=".docx",
            storage_ref="artifacts/art_1/report.docx",
            size_bytes=2048,
            content_hash="b" * 64,
        )
        ArtifactRepository.create_artifact(conn, artifact)

        v1 = ArtifactVersion(
            artifact_id=artifact.id,
            version_number=1,
            storage_ref="artifacts/art_1/v1/report.docx",
            size_bytes=2048,
            content_hash="b" * 64,
        )
        ArtifactRepository.create_artifact_version(conn, v1)

        # Attempt to insert identical version_number for same artifact
        v1_dup = ArtifactVersion(
            artifact_id=artifact.id,
            version_number=1,
            storage_ref="artifacts/art_1/v1_dup/report.docx",
            size_bytes=2048,
            content_hash="b" * 64,
        )
        with pytest.raises(sqlite3.IntegrityError):
            ArtifactRepository.create_artifact_version(conn, v1_dup)


def test_provenance_uniqueness_constraint(test_db_path: Path) -> None:
    """Verify that UNIQUE(artifact_id, artifact_hash) prevents duplicate provenance entries."""
    with get_connection(test_db_path) as conn:
        artifact = Artifact(
            title="Briefing Slides",
            artifact_type=ArtifactType.SLIDE,
            file_format=".pptx",
            storage_ref="artifacts/art_2/slides.pptx",
            size_bytes=4096,
            content_hash="c" * 64,
        )
        ArtifactRepository.create_artifact(conn, artifact)

        prov = ProvenanceRecord(
            artifact_id=artifact.id,
            artifact_hash="c" * 64,
            source_hashes=["d" * 64],
            generator_name="GenOffice.SlideDeckGenerator",
            model_version="1.0.0",
        )
        ArtifactRepository.create_provenance_record(conn, prov)

        # Duplicate insertion must raise IntegrityError
        prov_dup = ProvenanceRecord(
            artifact_id=artifact.id,
            artifact_hash="c" * 64,
            source_hashes=["d" * 64],
            generator_name="GenOffice.SlideDeckGenerator",
            model_version="1.0.0",
        )
        with pytest.raises(sqlite3.IntegrityError):
            ArtifactRepository.create_provenance_record(conn, prov_dup)


def test_validation_result_and_provenance_retrieval(test_db_path: Path) -> None:
    """Verify ValidationResult persistence and normalized score handling."""
    with get_connection(test_db_path) as conn:
        artifact = Artifact(
            title="Market Analysis",
            artifact_type=ArtifactType.SHEET,
            file_format=".xlsx",
            storage_ref="artifacts/art_3/data.xlsx",
            size_bytes=8192,
            content_hash="e" * 64,
        )
        ArtifactRepository.create_artifact(conn, artifact)

        val = ValidationResult(
            artifact_id=artifact.id,
            is_valid=True,
            score=0.92,
            hallucination_check_passed=True,
            citations_verified=[
                CitationVerification(
                    claim="Revenue grew 14%",
                    source_id="src_99",
                    source_hash="f" * 64,
                    citation_text="Q3 revenue grew by 14% YoY",
                )
            ],
            warnings=[],
            errors=[],
        )
        ArtifactRepository.create_validation_result(conn, val)

        fetched_val = ArtifactRepository.get_validation_result(conn, artifact.id)
        assert fetched_val is not None
        assert fetched_val.is_valid is True
        assert fetched_val.score == 0.92
        assert len(fetched_val.citations_verified) == 1
        assert fetched_val.citations_verified[0].claim == "Revenue grew 14%"


def test_project_deletion_sets_child_relationships_to_null(test_db_path: Path) -> None:
    """Verify that deleting a Project preserves child records and sets project_id to NULL (ON DELETE SET NULL)."""
    with get_connection(test_db_path) as conn:
        # 1. Create Project
        project = Project(name="Parent Project to Delete")
        ProjectRepository.create_project(conn, project)

        # 2. Create child Source, Chat, Job, Artifact
        source = Source(
            project_id=project.id,
            name="retained_source.txt",
            source_type=SourceType.FILE,
            mime_type="text/plain",
            size_bytes=100,
            content_hash="1" * 64,
        )
        SourceRepository.create_source(conn, source)

        chat = ChatSession(project_id=project.id, title="Retained Chat")
        ChatRepository.create_session(conn, chat)

        job = TransformationJob(
            project_id=project.id,
            requested_formats=[OutputFormat.SUMMARY],
            configuration=GenerationConfig(),
        )
        JobRepository.create_job(conn, job)

        artifact = Artifact(
            project_id=project.id,
            title="Retained Deliverable",
            artifact_type=ArtifactType.DOC,
            file_format=".md",
            storage_ref="artifacts/art_ret/doc.md",
            size_bytes=200,
            content_hash="2" * 64,
        )
        ArtifactRepository.create_artifact(conn, artifact)

        # 3. Delete Project
        ProjectRepository.delete_project(conn, project.id)

        # 4. Verify Project is deleted
        assert ProjectRepository.get_project(conn, project.id) is None

        # 5. Verify all children exist with project_id == None
        fetched_src = SourceRepository.get_source(conn, source.id)
        assert fetched_src is not None
        assert fetched_src.project_id is None

        fetched_chat = ChatRepository.get_session(conn, chat.id)
        assert fetched_chat is not None
        assert fetched_chat.project_id is None

        fetched_job = JobRepository.get_job(conn, job.id)
        assert fetched_job is not None
        assert fetched_job.project_id is None

        fetched_art = ArtifactRepository.get_artifact(conn, artifact.id)
        assert fetched_art is not None
        assert fetched_art.project_id is None
