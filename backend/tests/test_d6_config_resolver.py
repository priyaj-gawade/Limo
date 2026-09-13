"""Unit tests for Phase D6.1: TransformationConfigResolver.

Verifies:
- Default config inheritance from CanonicalContent intent
- Structured overrides take precedence over canonical intent
- FeatureMode to OutputFormat mappings (especially SHEETS -> SPREADSHEET, not SUMMARY!)
- Canonical provenance binding (canonical_id and 64-char SHA-256 hash)
- Language validation and objective mapping
- Error handling on invalid/missing canonical content
"""

from datetime import datetime, timezone
import pytest

from app.exceptions import BadRequestError
from app.models.content import CanonicalContent, CanonicalIntent
from app.models.enums import CommunicationObjective, ContentStyle, DetailLevel, FeatureMode, OutputFormat
from app.models.generation_config import GenerationConfig, PresentationOptions
from app.services.transformation.config_resolver import TransformationConfigResolver


def make_test_canonical(
    canonical_id: str = "can_test123",
    title: str = "Quarterly Threat Intelligence Report",
    primary_purpose: str = "Alert CISO and security operations to active zero-day exploit in VPN gateways",
    target_audiences: list = None,
    content_hash: str = "a" * 64,
) -> CanonicalContent:
    """Helper to construct a valid CanonicalContent fixture."""
    return CanonicalContent(
        id=canonical_id,
        source_ids=["src_test1"],
        title=title,
        context="Analysis of active intrusions targeting edge appliances.",
        intent=CanonicalIntent(
            primary_purpose=primary_purpose,
            target_audiences=target_audiences or ["Security Leadership", "SOC Analysts"],
            core_narrative="Patch edge gateways immediately to prevent remote exploitation.",
        ),
        entities=[],
        facts=[],
        claims=[],
        events=[],
        data_points=[],
        recommendations=["Disable external access until patched"],
        references=[],
        content_hash=content_hash,
        created_at=datetime.now(timezone.utc),
    )


def test_resolve_from_canonical_intent_only():
    """D6.1: Configuration inherits audience and mapped objective from CanonicalContent when no overrides exist."""
    resolver = TransformationConfigResolver()
    canonical = make_test_canonical(
        primary_purpose="Alert board of director members about critical cybersecurity risk",
        target_audiences=["Board of Directors", "Audit Committee"],
    )

    request = resolver.resolve(canonical=canonical)

    assert request.canonical_id == canonical.id
    assert request.canonical_hash == canonical.content_hash
    assert request.requested_formats == [OutputFormat.DOCUMENT]
    assert request.config.audience == "Board of Directors"
    assert request.config.objective == CommunicationObjective.ALERT


def test_structured_overrides_take_precedence():
    """D6.1: User/agent structured overrides take strict precedence over CanonicalContent defaults."""
    resolver = TransformationConfigResolver()
    canonical = make_test_canonical(
        primary_purpose="Inform engineering about library upgrade",
        target_audiences=["Software Engineers"],
    )

    overrides = GenerationConfig(
        audience="C-Suite",
        objective=CommunicationObjective.PERSUADE,
        style=ContentStyle.JOURNALISTIC,
        detail_level=DetailLevel.ANALYTICAL,
        presentation=PresentationOptions(slide_count=15, theme="dark_slate"),
    )

    request = resolver.resolve(
        canonical=canonical,
        structured_overrides=overrides,
        requested_formats=[OutputFormat.PRESENTATION],
        user_prompt="Prepare slide deck for investor pitch",
    )

    assert request.canonical_id == canonical.id
    assert request.requested_formats == [OutputFormat.PRESENTATION]
    assert request.config.audience == "C-Suite"
    assert request.config.objective == CommunicationObjective.PERSUADE
    assert request.config.style == ContentStyle.JOURNALISTIC
    assert request.config.detail_level == DetailLevel.ANALYTICAL
    assert request.config.presentation is not None
    assert request.config.presentation.slide_count == 15
    assert request.user_prompt == "Prepare slide deck for investor pitch"


def test_feature_mode_format_mappings():
    """D6.1: FeatureMode maps to authoritative OutputFormats (SHEETS -> SPREADSHEET, DOCS -> DOCUMENT, etc.)."""
    resolver = TransformationConfigResolver()
    canonical = make_test_canonical()

    # SHEETS MUST map to SPREADSHEET (MUST-FIX #1)
    req_sheets = resolver.resolve(canonical=canonical, active_mode=FeatureMode.SHEETS)
    assert req_sheets.requested_formats == [OutputFormat.SPREADSHEET]

    # DOCS MUST map to DOCUMENT (MUST-FIX #2)
    req_docs = resolver.resolve(canonical=canonical, active_mode=FeatureMode.DOCS)
    assert req_docs.requested_formats == [OutputFormat.DOCUMENT]

    # SLIDES MUST map to PRESENTATION
    req_slides = resolver.resolve(canonical=canonical, active_mode=FeatureMode.SLIDES)
    assert req_slides.requested_formats == [OutputFormat.PRESENTATION]

    # VIDEO MUST map to VIDEO
    req_video = resolver.resolve(canonical=canonical, active_mode=FeatureMode.VIDEO)
    assert req_video.requested_formats == [OutputFormat.VIDEO]

    # Explicit formats take precedence over FeatureMode
    req_explicit = resolver.resolve(
        canonical=canonical,
        requested_formats=[OutputFormat.ADVISORY, OutputFormat.SPREADSHEET],
        active_mode=FeatureMode.DOCS,
    )
    assert req_explicit.requested_formats == [OutputFormat.ADVISORY, OutputFormat.SPREADSHEET]


def test_canonical_provenance_binding():
    """D6.1: Cryptographic SHA-256 hash and ID from CanonicalContent are immutably bound."""
    resolver = TransformationConfigResolver()
    test_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    canonical = make_test_canonical(canonical_id="can_provenance999", content_hash=test_hash)

    request = resolver.resolve(canonical=canonical)

    assert request.canonical_id == "can_provenance999"
    assert request.canonical_hash == test_hash
    assert request.id.startswith("req_")


def test_invalid_canonical_content_fails():
    """D6.1: Reject missing or malformed CanonicalContent."""
    resolver = TransformationConfigResolver()

    # None canonical
    with pytest.raises(BadRequestError, match="CanonicalContent is required"):
        resolver.resolve(canonical=None)  # type: ignore[arg-type]

    # Malformed canonical ID
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        make_test_canonical(canonical_id="invalid_prefix_without_can")

    # Invalid hash length
    with pytest.raises(ValidationError):
        make_test_canonical(content_hash="too_short")


def test_invalid_language_code_fails():
    """D6.1: Reject invalid ISO language codes."""
    resolver = TransformationConfigResolver()
    canonical = make_test_canonical()

    bad_config = GenerationConfig(language="toolonglanguagecode123")
    with pytest.raises(BadRequestError, match="Invalid ISO language code"):
        resolver.resolve(canonical=canonical, structured_overrides=bad_config)


def test_purpose_to_objective_mapping():
    """D6.1: Deterministically map canonical purpose statements to CommunicationObjective."""
    resolver = TransformationConfigResolver()

    assert resolver._map_purpose_to_objective("Alert CISO to zero-day exploit") == CommunicationObjective.ALERT
    assert resolver._map_purpose_to_objective("Persuade committee to approve budget proposal") == CommunicationObjective.PERSUADE
    assert resolver._map_purpose_to_objective("Educate staff on cybersecurity hygiene") == CommunicationObjective.EDUCATE
    assert resolver._map_purpose_to_objective("Synthesize multi-source intelligence") == CommunicationObjective.SYNTHESIZE
    assert resolver._map_purpose_to_objective("Quarterly status update") == CommunicationObjective.INFORM
