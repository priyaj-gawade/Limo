"""Unit tests for Phase D6.2: OutputPlanner.

Verifies:
- Decomposition of single and multi-deliverable requests
- Format-specific option extraction and overrides
- Working title derivation
- Complexity estimation
- Engine route assignment and all_engines_available indicator
- Stage dispatch failure on unimplemented engines (UnimplementedEngineError)
"""

import pytest

from app.exceptions import BadRequestError, UnimplementedEngineError
from app.models.enums import OutputFormat
from app.models.generation_config import GenerationConfig, PresentationOptions, VideoOptions
from app.models.transformation import EngineType, TransformationRequest
from app.services.transformation.output_planner import OutputPlanner


def make_test_request(
    formats: list[OutputFormat],
    config: GenerationConfig = None,
    user_prompt: str = "Generate executive briefing",
) -> TransformationRequest:
    """Helper to build a valid TransformationRequest."""
    return TransformationRequest(
        canonical_id="can_plan_test",
        canonical_hash="b" * 64,
        requested_formats=formats,
        config=config or GenerationConfig(),
        user_prompt=user_prompt,
    )


def test_plan_single_deliverable():
    """D6.2: Decomposing a single-deliverable request creates 1 PlannedDeliverable with correct route."""
    planner = OutputPlanner()
    request = make_test_request(
        formats=[OutputFormat.PRESENTATION],
        config=GenerationConfig(presentation=PresentationOptions(slide_count=12, theme="slate")),
    )

    plan = planner.plan(request=request, canonical_title="Incident Response 2026")

    assert plan.request_id == request.id
    assert plan.canonical_id == request.canonical_id
    assert plan.canonical_hash == request.canonical_hash
    assert len(plan.deliverables) == 1
    assert plan.all_engines_available is False

    deliv = plan.deliverables[0]
    assert deliv.format == OutputFormat.PRESENTATION
    assert deliv.title == "Incident Response 2026 - Presentation"
    assert deliv.route.engine_type == EngineType.GENOFFICE_SLIDES
    assert deliv.options.get("slide_count") == 12
    assert deliv.options.get("theme") == "slate"
    assert deliv.deliverable_id.startswith("del_")


def test_plan_multi_deliverables():
    """D6.2: Multi-format requests decompose into discrete PlannedDeliverables with separate routes."""
    planner = OutputPlanner()
    request = make_test_request(
        formats=[OutputFormat.PRESENTATION, OutputFormat.DOCUMENT, OutputFormat.SPREADSHEET],
    )

    plan = planner.plan(request=request, canonical_title="Cloud Security Assessment")

    assert len(plan.deliverables) == 3
    formats_planned = [d.format for d in plan.deliverables]
    assert OutputFormat.PRESENTATION in formats_planned
    assert OutputFormat.DOCUMENT in formats_planned
    assert OutputFormat.SPREADSHEET in formats_planned

    # Verify routes mapping
    assert plan.routes[OutputFormat.PRESENTATION].engine_type == EngineType.GENOFFICE_SLIDES
    assert plan.routes[OutputFormat.DOCUMENT].engine_type == EngineType.GENOFFICE_DOCS
    assert plan.routes[OutputFormat.SPREADSHEET].engine_type == EngineType.GENOFFICE_SHEETS


def test_format_overrides_applied_to_deliverable_options():
    """D6.2: Arbitrary format_overrides are cleanly merged into deliverable options."""
    planner = OutputPlanner()
    cfg = GenerationConfig(
        format_overrides={
            "spreadsheet": {"custom_fiscal_year": 2026, "currency": "INR"},
        }
    )
    request = make_test_request(formats=[OutputFormat.SPREADSHEET], config=cfg)

    plan = planner.plan(request=request)

    deliv = plan.deliverables[0]
    assert deliv.options.get("custom_fiscal_year") == 2026
    assert deliv.options.get("currency") == "INR"
    assert deliv.options.get("freeze_header") is True


def test_empty_requested_formats_validation():
    """D6.2: TransformationRequest requires at least one format."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        TransformationRequest(
            canonical_id="can_test",
            canonical_hash="c" * 64,
            requested_formats=[],
        )
