"""Unit tests for Phase D6.3: EngineRouter.

Verifies:
- Authoritative routing directory mapping for all 12 OutputFormats
- Strict designation of target phases and extensions
- Native adapters (Markdown, HTML, LinkedIn, Twitter, Infographic) marked is_implemented=True in D6.3
- External engines (Docs, Slides, Sheets, Video, PDF, Advisory, Summary) strictly marked is_implemented=False
- Explicit failure contract: dispatch on unimplemented external engine raises UnimplementedEngineError (HTTP 501)
- Rejection of unrecognized formats with UnsupportedFormatError (HTTP 400)
- Contract generation via router.build_contract()
- Zero mock or fake deliverables generated
"""

from datetime import datetime, timezone
import pytest
from fastapi import status

from app.exceptions import UnimplementedEngineError, UnsupportedFormatError
from app.models.content import CanonicalContent, CanonicalIntent
from app.models.enums import OutputFormat
from app.models.generation_config import GenerationConfig
from app.models.generation_contracts import GenOfficePayload, VideoEnginePayload
from app.models.transformation import EngineType, PlannedDeliverable
from app.services.transformation.engine_router import EngineRouter


@pytest.fixture
def dummy_canonical():
    return CanonicalContent(
        source_ids=["src_dummy"],
        title="Router Contract Test",
        context="Testing contract generation in engine router.",
        intent=CanonicalIntent(
            primary_purpose="Test router contract creation",
            target_audiences=["Test"],
            core_narrative="Ensures router builds contracts cleanly.",
        ),
        content_hash="f" * 64,
        created_at=datetime.now(timezone.utc),
    )


def test_routing_table_completeness():
    """D6.3: Every OutputFormat routes to its authoritative engine and expected file extension."""
    router = EngineRouter()

    # 1. GenOffice Core Office (Phase D7)
    route_doc = router.get_route(OutputFormat.DOCUMENT)
    assert route_doc.engine_type == EngineType.GENOFFICE_DOCS
    assert route_doc.target_extension == ".docx"
    assert "D7" in route_doc.target_phase

    route_pres = router.get_route(OutputFormat.PRESENTATION)
    assert route_pres.engine_type == EngineType.GENOFFICE_SLIDES
    assert route_pres.target_extension == ".pptx"
    assert "D7" in route_pres.target_phase

    route_sheets = router.get_route(OutputFormat.SPREADSHEET)
    assert route_sheets.engine_type == EngineType.GENOFFICE_SHEETS
    assert route_sheets.target_extension == ".xlsx"
    assert "D7" in route_sheets.target_phase

    route_adv = router.get_route(OutputFormat.ADVISORY)
    assert route_adv.engine_type == EngineType.GENOFFICE_DOCS
    assert route_adv.target_extension == ".docx"

    route_sum = router.get_route(OutputFormat.SUMMARY)
    assert route_sum.engine_type == EngineType.GENOFFICE_DOCS
    assert route_sum.target_extension == ".docx"

    route_pdf = router.get_route(OutputFormat.PDF)
    assert route_pdf.engine_type == EngineType.GENOFFICE_DOCS
    assert route_pdf.target_extension == ".pdf"

    # 2. Video Engine (Phase D8)
    route_video = router.get_route(OutputFormat.VIDEO)
    assert route_video.engine_type == EngineType.VIDEO_ENGINE
    assert route_video.target_extension == ".mp4"
    assert "D8" in route_video.target_phase

    # 3. Native Social & Media (Phase D6.3)
    route_linkedin = router.get_route(OutputFormat.LINKEDIN)
    assert route_linkedin.engine_type == EngineType.NATIVE_SOCIAL
    assert route_linkedin.target_extension == ".md"
    assert "D6.3" in route_linkedin.target_phase

    route_twitter = router.get_route(OutputFormat.TWITTER)
    assert route_twitter.engine_type == EngineType.NATIVE_SOCIAL
    assert route_twitter.target_extension == ".json"

    route_info = router.get_route(OutputFormat.INFOGRAPHIC)
    assert route_info.engine_type == EngineType.NATIVE_INFOGRAPHIC
    assert route_info.target_extension == ".svg"

    route_md = router.get_route(OutputFormat.MARKDOWN)
    assert route_md.engine_type == EngineType.NATIVE_MARKDOWN
    assert route_md.target_extension == ".md"

    route_html = router.get_route(OutputFormat.HTML)
    assert route_html.engine_type == EngineType.NATIVE_MARKDOWN
    assert route_html.target_extension == ".html"


def test_engine_implementation_status_in_d6_3():
    """D6.3: Native adapters are is_implemented=True; external engines remain is_implemented=False."""
    router = EngineRouter()
    native_formats = {
        OutputFormat.MARKDOWN,
        OutputFormat.HTML,
        OutputFormat.LINKEDIN,
        OutputFormat.TWITTER,
        OutputFormat.INFOGRAPHIC,
    }
    external_formats = {
        OutputFormat.DOCUMENT,
        OutputFormat.PRESENTATION,
        OutputFormat.SPREADSHEET,
        OutputFormat.ADVISORY,
        OutputFormat.SUMMARY,
        OutputFormat.PDF,
        OutputFormat.VIDEO,
    }

    for fmt in native_formats:
        route = router.get_route(fmt)
        assert route.is_implemented is True, f"Native engine for {fmt} must be is_implemented=True in D6.3"

    for fmt in external_formats:
        route = router.get_route(fmt)
        assert route.is_implemented is False, f"External engine for {fmt} must be is_implemented=False in D6.3"


def test_explicit_failure_on_unimplemented_engine():
    """D6.3: Dispatching an unbuilt external engine raises UnimplementedEngineError (HTTP 501), zero fake generation."""
    router = EngineRouter()

    # GenOffice Docs
    route_docs = router.get_route(OutputFormat.DOCUMENT)
    with pytest.raises(UnimplementedEngineError) as exc_info:
        router.dispatch(route=route_docs)

    err = exc_info.value
    assert err.status_code == status.HTTP_501_NOT_IMPLEMENTED
    assert err.error_code == "UNIMPLEMENTED_ENGINE"
    assert "genoffice_docs" in err.message
    assert "D7" in err.message

    # Video Engine
    route_video = router.get_route(OutputFormat.VIDEO)
    with pytest.raises(UnimplementedEngineError) as exc_info_v:
        router.dispatch(route=route_video)
    assert exc_info_v.value.status_code == status.HTTP_501_NOT_IMPLEMENTED
    assert "video_engine" in exc_info_v.value.message


def test_unsupported_format_raises_error():
    """D6.3: Rejection of unknown/invalid formats with UnsupportedFormatError (HTTP 400)."""
    router = EngineRouter()

    with pytest.raises(UnsupportedFormatError) as exc_info:
        router.get_route("nonexistent_hologram_format")  # type: ignore[arg-type]

    err = exc_info.value
    assert err.status_code == status.HTTP_400_BAD_REQUEST
    assert err.error_code == "BAD_REQUEST"
    assert "nonexistent_hologram_format" in err.message


def test_build_contract_via_router(dummy_canonical):
    """D6.3: EngineRouter.build_contract delegates to GenerationContractBuilder for external engines."""
    router = EngineRouter()

    # 1. GenOffice Slides Contract
    deliv_slides = PlannedDeliverable(
        deliverable_id="del_slides_test",
        format=OutputFormat.PRESENTATION,
        title="Slides Contract Test",
        route=router.get_route(OutputFormat.PRESENTATION),
    )
    contract_slides = router.build_contract(
        deliverable=deliv_slides,
        canonical=dummy_canonical,
        config=GenerationConfig(),
    )
    assert isinstance(contract_slides, GenOfficePayload)
    assert contract_slides.type == "presentation"

    # 2. Video Contract
    deliv_video = PlannedDeliverable(
        deliverable_id="del_video_test",
        format=OutputFormat.VIDEO,
        title="Video Contract Test",
        route=router.get_route(OutputFormat.VIDEO),
    )
    contract_video = router.build_contract(
        deliverable=deliv_video,
        canonical=dummy_canonical,
        config=GenerationConfig(),
    )
    assert isinstance(contract_video, VideoEnginePayload)
    assert contract_video.title == "Video Contract Test"

    # 3. Native Deliverable Contract
    deliv_md = PlannedDeliverable(
        deliverable_id="del_md_test",
        format=OutputFormat.MARKDOWN,
        title="Markdown Contract Test",
        route=router.get_route(OutputFormat.MARKDOWN),
    )
    contract_md = router.build_contract(
        deliverable=deliv_md,
        canonical=dummy_canonical,
        config=GenerationConfig(),
    )
    assert isinstance(contract_md, dict)
    assert contract_md["format"] == "markdown"
    assert contract_md["filename"].endswith(".md")


def test_list_supported_formats():
    """D6.3: Returns all 12 recognized formats."""
    router = EngineRouter()
    supported = router.list_supported_formats()
    assert len(supported) == 12
    assert OutputFormat.DOCUMENT in supported
    assert OutputFormat.SPREADSHEET in supported
    assert OutputFormat.PRESENTATION in supported
    assert OutputFormat.VIDEO in supported
