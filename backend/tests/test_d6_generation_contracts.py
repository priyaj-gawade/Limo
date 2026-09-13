"""Unit tests for Generation Contracts (Phase D6.3).

Verifies:
- GenOfficePayload construction conforming to GenOffice Electron Main (POST /api/v1/generate)
- VideoEnginePayload construction conforming to the versioned contract designed for future D8 adapter
- Provenance grounding (canonical_id, canonical_hash preserved across all payloads)
- Zero external binary execution (pure contract generation)
"""

from datetime import datetime, timezone
import pytest

from app.models.content import (
    CanonicalContent,
    CanonicalDataPoint,
    CanonicalEvent,
    CanonicalFact,
    CanonicalIntent,
)
from app.models.enums import OutputFormat
from app.models.generation_config import GenerationConfig, PresentationOptions, VideoOptions
from app.models.generation_contracts import GenOfficePayload, VideoEnginePayload
from app.models.transformation import EngineRoute, EngineType, PlannedDeliverable
from app.services.transformation.contracts import GenerationContractBuilder


@pytest.fixture
def sample_canonical() -> CanonicalContent:
    """Construct grounded CanonicalContent for contract generation testing."""
    return CanonicalContent(
        source_ids=["src_test_001"],
        title="Enterprise Telemetry Incident Report",
        context="Investigation into critical firmware vulnerability within edge gateway infrastructure.",
        intent=CanonicalIntent(
            primary_purpose="Brief leadership on security posture and patch compliance",
            target_audiences=["Executive Board", "Security Operations"],
            core_narrative="Gateway firmware < 4.2 requires emergency mitigation within 48 hours.",
        ),
        facts=[
            CanonicalFact(
                statement="Edge gateways running v4.1 expose unauthenticated RPC endpoints.",
                confidence=0.98,
                evidence_status="verified",
                source_reference="Section 2.1",
            ),
            CanonicalFact(
                statement="Telemetry spoofing was observed in 3 regional zones.",
                confidence=0.92,
                evidence_status="verified",
                source_reference="Section 3.4",
            ),
        ],
        data_points=[
            CanonicalDataPoint(metric="Exposed Gateways", value="142", unit="units", context="Global fleet"),
            CanonicalDataPoint(metric="Patch Compliance", value="18.5%", unit="percent", context="Initial audit"),
        ],
        events=[
            CanonicalEvent(title="Anomaly Detected", timestamp_desc="Day 1 04:00 UTC", significance="Initial alert"),
            CanonicalEvent(title="Containment Deployed", timestamp_desc="Day 2 12:00 UTC", significance="Isolation active"),
        ],
        recommendations=[
            "Deploy emergency firmware patch v4.2.1 immediately.",
            "Restrict WAN RPC ports on all perimeter firewalls.",
        ],
        content_hash="a" * 64,
        created_at=datetime.now(timezone.utc),
    )


def test_genoffice_presentation_contract(sample_canonical):
    """D6.3: GenOffice presentation contract conforms to POST /api/v1/generate schema."""
    deliv = PlannedDeliverable(
        deliverable_id="del_presentation_01",
        format=OutputFormat.PRESENTATION,
        title="Executive Cyber Defense Briefing",
        route=EngineRoute(
            format=OutputFormat.PRESENTATION,
            engine_type=EngineType.GENOFFICE_SLIDES,
            target_extension=".pptx",
            is_implemented=False,
            target_phase="D7 (GenOffice)",
        ),
    )
    cfg = GenerationConfig(
        presentation=PresentationOptions(slide_count=10, theme="cyber_dark"),
        audience="Board of Directors",
        tone="urgent",
    )

    payload = GenerationContractBuilder.build_genoffice_payload(
        canonical=sample_canonical,
        deliverable=deliv,
        config=cfg,
        project_id="proj_alpha",
        session_id="sess_briefing",
    )

    assert isinstance(payload, GenOfficePayload)
    assert payload.type == "presentation"
    assert payload.project_id == "proj_alpha"
    assert payload.session_id == "sess_briefing"
    assert "Executive Cyber Defense Briefing" in payload.prompt
    assert payload.options.title == "Executive Cyber Defense Briefing"
    assert payload.options.approx_pages == 10
    assert payload.options.theme == "cyber_dark"
    assert payload.options.audience == "Board of Directors"
    assert payload.options.canonical_id == sample_canonical.id
    assert payload.options.canonical_hash == sample_canonical.content_hash
    assert len(payload.options.sections_outline) >= 4

    # Serialization test
    payload_json = payload.model_dump_json()
    assert sample_canonical.id in payload_json
    assert "presentation" in payload_json


def test_genoffice_document_contract(sample_canonical):
    """D6.3: GenOffice document contract produces valid Word/Docs configuration."""
    deliv = PlannedDeliverable(
        deliverable_id="del_doc_01",
        format=OutputFormat.DOCUMENT,
        title="Telemetry Security Technical Report",
        route=EngineRoute(
            format=OutputFormat.DOCUMENT,
            engine_type=EngineType.GENOFFICE_DOCS,
            target_extension=".docx",
            is_implemented=False,
            target_phase="D7 (GenOffice)",
        ),
    )
    cfg = GenerationConfig(audience="Engineering Leadership")

    payload = GenerationContractBuilder.build_genoffice_payload(
        canonical=sample_canonical,
        deliverable=deliv,
        config=cfg,
    )

    assert payload.type == "document"
    assert payload.options.canonical_id == sample_canonical.id
    assert payload.options.approx_pages == 5


def test_video_engine_contract(sample_canonical):
    """D6.3: Video engine contract builds a versioned payload designed for future D8 adapter."""
    deliv = PlannedDeliverable(
        deliverable_id="del_video_01",
        format=OutputFormat.VIDEO,
        title="Incident Explainer Video",
        route=EngineRoute(
            format=OutputFormat.VIDEO,
            engine_type=EngineType.VIDEO_ENGINE,
            target_extension=".mp4",
            is_implemented=False,
            target_phase="D8 (Video Engine)",
        ),
    )
    cfg = GenerationConfig(
        video=VideoOptions(target_duration_sec=60, aspect_ratio="16:9"),
    )

    payload = GenerationContractBuilder.build_video_payload(
        canonical=sample_canonical,
        deliverable=deliv,
        config=cfg,
    )

    assert isinstance(payload, VideoEnginePayload)
    assert payload.title == "Incident Explainer Video"
    assert payload.canonical_id == sample_canonical.id
    assert payload.canonical_hash == sample_canonical.content_hash
    assert len(payload.script_blueprint) >= 3

    # Check first scene (hook)
    first_scene = payload.script_blueprint[0]
    assert first_scene.scene_index == 1
    assert "Incident Explainer Video" in first_scene.visual_cue
    assert sample_canonical.intent.core_narrative in first_scene.narration_text

    # Check visual & audio configuration
    assert payload.visual_config["aspect_ratio"] == "16:9"
    assert payload.visual_config["visual_style"] == "corporate_clean"
    assert payload.audio_config["language"] == "en"

    # Total duration conforms to length limits
    assert 10 <= payload.estimated_duration_seconds <= 60
