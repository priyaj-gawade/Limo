"""Tests for D3.2: Shared domain models, validation, and serialization."""

import pytest
from pydantic import ValidationError

from app.models import (
    Artifact,
    ArtifactType,
    ArtifactVersion,
    CanonicalClaim,
    CanonicalContent,
    CanonicalDataPoint,
    CanonicalEntity,
    CanonicalEvent,
    CanonicalFact,
    CanonicalIntent,
    CanonicalReference,
    ChatSession,
    CitationVerification,
    CommunicationObjective,
    ContentStyle,
    DetailLevel,
    FeatureMode,
    GenerationConfig,
    JobState,
    TransformationJob,
    Message,
    MessageAttachment,
    MessageRole,
    OutputFormat,
    Project,
    ProvenanceRecord,
    Source,
    SourceType,
    ValidationResult,
    ValidationStatus,
)

SAMPLE_SHA256_1 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
SAMPLE_SHA256_2 = "a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e"


def test_project_model():
    """Verify Project creation, stable ID generation, and serialization."""
    proj = Project(name="Critical Infrastructure Review")
    assert proj.id.startswith("proj_")
    assert proj.name == "Critical Infrastructure Review"

    # Round trip
    dump = proj.model_dump_json()
    reconstructed = Project.model_validate_json(dump)
    assert reconstructed.id == proj.id
    assert reconstructed.name == proj.name

    # Invalid ID prefix
    with pytest.raises(ValidationError):
        Project(id="invalid_123", name="Bad ID")


def test_source_model():
    """Verify Source model with SHA-256 hash and internal storage reference."""
    src = Source(
        name="telemetry_log.csv",
        source_type=SourceType.TABULAR,
        mime_type="text/csv",
        storage_ref="sources/src_123/telemetry_log.csv",
        size_bytes=1024,
        content_hash=SAMPLE_SHA256_1
    )
    assert src.id.startswith("src_")
    assert src.content_hash == SAMPLE_SHA256_1
    assert src.storage_ref == "sources/src_123/telemetry_log.csv"

    # Invalid SHA-256
    with pytest.raises(ValidationError):
        Source(
            name="test.txt",
            source_type=SourceType.FILE,
            mime_type="text/plain",
            size_bytes=10,
            content_hash="not-a-valid-sha256"
        )


def test_chat_session_model():
    """Verify ChatSession model with FeatureMode."""
    chat = ChatSession(title="Slide Deck Strategy", mode=FeatureMode.SLIDES)
    assert chat.id.startswith("chat_")
    assert chat.mode == FeatureMode.SLIDES

    dump = chat.model_dump_json()
    reconstructed = ChatSession.model_validate_json(dump)
    assert reconstructed.id == chat.id
    assert reconstructed.mode == FeatureMode.SLIDES


def test_message_rejects_chain_of_thought():
    """Verify strict rule: Message model rejects private chain-of-thought persistence."""
    # Valid message
    msg = Message(
        session_id="chat_123",
        role=MessageRole.ASSISTANT,
        content="Here is the executive summary.",
        execution_summary="3 factual claims synthesized from 2 sources."
    )
    assert msg.id.startswith("msg_")
    assert msg.execution_summary is not None

    # Prohibited: chain_of_thought field
    with pytest.raises(ValidationError, match="private model chain-of-thought"):
        Message.model_validate({
            "id": "msg_1234567890abcdef",
            "session_id": "chat_123",
            "role": "assistant",
            "content": "Result",
            "chain_of_thought": "Secret private reasoning step 1 -> step 2"
        })

    # Prohibited: thinking_process field
    with pytest.raises(ValidationError, match="private model chain-of-thought"):
        Message.model_validate({
            "id": "msg_1234567890abcdef",
            "session_id": "chat_123",
            "role": "assistant",
            "content": "Result",
            "thinking_process": "Raw reasoning scratchpad"
        })


def test_generation_config_and_transformation_job():
    """Verify TransformationJob and GenerationConfig with OutputFormat enums."""
    config = GenerationConfig(
        audience="Technical",
        tone="Authoritative",
        language="en",
        detail_level=DetailLevel.ANALYTICAL,
        objective=CommunicationObjective.ALERT,
        style=ContentStyle.CORPORATE,
        format_overrides={"slides_count": 12}
    )

    job = TransformationJob(
        project_id="proj_123",
        requested_formats=[OutputFormat.PRESENTATION, OutputFormat.ADVISORY],
        configuration=config,
        state=JobState.QUEUED,
        progress=0.0
    )
    assert job.id.startswith("job_")
    assert len(job.requested_formats) == 2
    assert OutputFormat.PRESENTATION in job.requested_formats
    assert OutputFormat.ADVISORY in job.requested_formats

    # OutputFormat is distinct from FeatureMode
    assert OutputFormat.PRESENTATION.value == "presentation"
    assert FeatureMode.SLIDES.value == "slides"

    dump = job.model_dump_json()
    reconstructed = TransformationJob.model_validate_json(dump)
    assert reconstructed.id == job.id
    assert reconstructed.configuration.detail_level == DetailLevel.ANALYTICAL


def test_canonical_content_model():
    """Verify rich CanonicalContent model matches SRS requirements."""
    can = CanonicalContent(
        source_ids=["src_1", "src_2"],
        title="National SCADA Telemetry Synthesis",
        context="National energy and water SCADA sensor telemetry audit.",
        intent=CanonicalIntent(
            primary_purpose="Alert leadership to distributed spoofing anomalies",
            target_audiences=["Executive Board", "Security Operations"],
            core_narrative="Distributed sensor spoofing detected across primary energy feeders.",
            urgency_level="Immediate"
        ),
        entities=[
            CanonicalEntity(name="SCADA Feed Alpha", category="Sensor System", relevance_score=0.95),
            CanonicalEntity(name="National Grid Operator", category="Organization", relevance_score=0.9)
        ],
        facts=[
            CanonicalFact(statement="142 spoofing incidents reported across sector A.", source_id="src_1", confidence=0.99)
        ],
        claims=[
            CanonicalClaim(claim="Anomalous control loops indicate coordinated reconnaissance.", claimant="Lead Analyst")
        ],
        events=[
            CanonicalEvent(title="Telemetry Spike Occurred", timestamp_desc="2026-09-08 04:15 UTC")
        ],
        data_points=[
            CanonicalDataPoint(metric="Telemetry spoofing incidents", value="142", unit="incidents")
        ],
        recommendations=[
            "Mandate cryptographic mutual authentication on all SCADA loops."
        ],
        references=[
            CanonicalReference(citation_key="[REF-1]", title="SCADA Telemetry Audit Log Q3")
        ],
        content_hash=SAMPLE_SHA256_1
    )
    assert can.id.startswith("can_")
    assert len(can.entities) == 2
    assert len(can.facts) == 1
    assert len(can.recommendations) == 1

    dump = can.model_dump_json()
    reconstructed = CanonicalContent.model_validate_json(dump)
    assert reconstructed.id == can.id
    assert reconstructed.intent.primary_purpose == can.intent.primary_purpose


def test_artifact_and_artifact_version():
    """Verify Artifact uses internal storage_ref and validates format/hash."""
    art = Artifact(
        title="Threat Analysis Briefing",
        artifact_type=ArtifactType.DOC,
        file_format="docx",
        storage_ref="artifacts/art_100/briefing.docx",
        size_bytes=45000,
        content_hash=SAMPLE_SHA256_1,
        stats="4 Pages • 1,600 Words • DOCX",
        version=1,
        validation_status=ValidationStatus.VALID
    )
    assert art.id.startswith("art_")
    assert art.file_format == ".docx"  # Prepends dot automatically if missing
    assert art.storage_ref == "artifacts/art_100/briefing.docx"

    ver = ArtifactVersion(
        artifact_id=art.id,
        version_number=1,
        storage_ref=art.storage_ref,
        size_bytes=art.size_bytes,
        content_hash=art.content_hash,
        change_summary="Initial generation"
    )
    assert ver.id.startswith("ver_")
    assert ver.version_number == 1


def test_validation_result_and_provenance_record():
    """Verify ValidationResult normalized score (0.0-1.0) and ProvenanceRecord."""
    # Valid score
    val = ValidationResult(
        artifact_id="art_123",
        is_valid=True,
        score=0.92,
        hallucination_check_passed=True,
        citations_verified=[
            CitationVerification(
                claim="142 incidents reported",
                source_id="src_1",
                source_hash=SAMPLE_SHA256_1,
                citation_text="Log indicates 142 discrete events",
                similarity_score=0.96
            )
        ]
    )
    assert val.id.startswith("val_")
    assert val.score == 0.92

    # Score out of range: must fail
    with pytest.raises(ValidationError):
        ValidationResult(
            artifact_id="art_123",
            is_valid=True,
            score=1.5  # > 1.0 must raise error
        )

    with pytest.raises(ValidationError):
        ValidationResult(
            artifact_id="art_123",
            is_valid=True,
            score=-0.1  # < 0.0 must raise error
        )

    # Provenance Record
    prov = ProvenanceRecord(
        artifact_id="art_123",
        artifact_hash=SAMPLE_SHA256_2,
        source_hashes=[SAMPLE_SHA256_1],
        canonical_content_hash=SAMPLE_SHA256_1,
        generator_name="GenOffice.DocumentGenerator",
        model_version="1.0.0"
    )
    assert prov.id.startswith("prov_")
    assert prov.artifact_hash == SAMPLE_SHA256_2
    assert len(prov.source_hashes) == 1


def test_model_invalid_inputs_systematic():
    """Verify systematic input validation across domain models."""
    # 1. Source: negative size_bytes
    with pytest.raises(ValidationError):
        Source(
            name="invalid_size.txt",
            source_type=SourceType.FILE,
            mime_type="text/plain",
            size_bytes=-5,
            content_hash=SAMPLE_SHA256_1,
        )

    # 2. Source: non-hex or bad length hash
    with pytest.raises(ValidationError):
        Source(
            name="invalid_hash.txt",
            source_type=SourceType.FILE,
            mime_type="text/plain",
            size_bytes=10,
            content_hash="not_a_valid_hex_hash",
        )

    # 3. TransformationJob: empty requested_formats
    with pytest.raises(ValidationError):
        TransformationJob(
            requested_formats=[],  # min_length=1
            configuration=GenerationConfig(),
        )

    # 4. TransformationJob: progress out of range
    with pytest.raises(ValidationError):
        TransformationJob(
            requested_formats=[OutputFormat.SUMMARY],
            configuration=GenerationConfig(),
            progress=1.5,
        )
    with pytest.raises(ValidationError):
        TransformationJob(
            requested_formats=[OutputFormat.SUMMARY],
            configuration=GenerationConfig(),
            progress=-0.2,
        )

    # 5. Artifact: invalid format or negative size
    with pytest.raises(ValidationError):
        Artifact(
            title="Bad Artifact",
            artifact_type=ArtifactType.DOC,
            file_format=".md",
            storage_ref="artifacts/art_1/doc.md",
            size_bytes=-100,
            content_hash=SAMPLE_SHA256_1,
        )

    # 6. ArtifactVersion: version_number < 1
    with pytest.raises(ValidationError):
        ArtifactVersion(
            artifact_id="art_123",
            version_number=0,  # ge=1
            storage_ref="artifacts/art_123/v0.md",
            size_bytes=100,
            content_hash=SAMPLE_SHA256_1,
        )


def test_all_models_serialization_roundtrip():
    """Verify that every domain model supports lossless JSON serialization & deserialization."""
    # 1. Project
    proj = Project(name="Roundtrip Project", description="Serialization test")
    assert Project.model_validate_json(proj.model_dump_json()).id == proj.id

    # 2. Source
    src = Source(
        name="roundtrip.csv",
        source_type=SourceType.TABULAR,
        mime_type="text/csv",
        storage_ref="sources/src_rt/roundtrip.csv",
        size_bytes=512,
        content_hash=SAMPLE_SHA256_1,
    )
    assert Source.model_validate_json(src.model_dump_json()).id == src.id

    # 3. ChatSession
    chat = ChatSession(title="Roundtrip Chat", mode=FeatureMode.DOCS)
    assert ChatSession.model_validate_json(chat.model_dump_json()).id == chat.id

    # 4. Message
    msg = Message(
        session_id=chat.id,
        role=MessageRole.USER,
        content="Roundtrip message content",
        attachments=[
            MessageAttachment(
                id="att_rt",
                name="test.json",
                size_bytes=256,
                mime_type="application/json",
            )
        ],
    )
    assert Message.model_validate_json(msg.model_dump_json()).id == msg.id

    # 5. TransformationJob
    job = TransformationJob(
        prompt="Roundtrip prompt",
        source_ids=[src.id],
        requested_formats=[OutputFormat.PRESENTATION, OutputFormat.SUMMARY],
        configuration=GenerationConfig(),
    )
    assert TransformationJob.model_validate_json(job.model_dump_json()).id == job.id

    # 6. CanonicalContent
    can = CanonicalContent(
        job_id=job.id,
        source_ids=[src.id],
        title="Roundtrip Synthesis",
        context="Briefing on Q3 telemetry findings",
        content_hash=SAMPLE_SHA256_1,
        intent=CanonicalIntent(
            primary_purpose="Briefing",
            target_audiences=["Board"],
            core_narrative="Strong performance",
        ),
        claims=[
            CanonicalClaim(
                id="clm_rt",
                claim="Revenue grew 22%",
            )
        ],
    )
    assert CanonicalContent.model_validate_json(can.model_dump_json()).id == can.id

    # 7. Artifact & Version
    art = Artifact(
        title="Roundtrip Artifact",
        artifact_type=ArtifactType.DOC,
        file_format=".md",
        storage_ref="artifacts/art_rt/doc.md",
        size_bytes=1024,
        content_hash=SAMPLE_SHA256_2,
    )
    assert Artifact.model_validate_json(art.model_dump_json()).id == art.id

    ver = ArtifactVersion(
        artifact_id=art.id,
        version_number=1,
        storage_ref=art.storage_ref,
        size_bytes=art.size_bytes,
        content_hash=art.content_hash,
    )
    assert ArtifactVersion.model_validate_json(ver.model_dump_json()).id == ver.id

    # 8. ValidationResult & Provenance
    val = ValidationResult(
        artifact_id=art.id,
        is_valid=True,
        score=0.88,
        hallucination_check_passed=True,
    )
    assert ValidationResult.model_validate_json(val.model_dump_json()).id == val.id

    prov = ProvenanceRecord(
        artifact_id=art.id,
        artifact_hash=SAMPLE_SHA256_2,
        source_hashes=[SAMPLE_SHA256_1],
        generator_name="GenOffice.TestGenerator",
        model_version="1.0.0",
    )
    assert ProvenanceRecord.model_validate_json(prov.model_dump_json()).id == prov.id
