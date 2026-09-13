"""Unit tests for Phase D3.9: GenerationConfig and typed output-specific options."""

import pytest

from app.models.enums import (
    CommunicationObjective,
    ContentStyle,
    DetailLevel,
    OutputFormat,
)
from app.models.generation_config import (
    DocumentOptions,
    GenerationConfig,
    InfographicOptions,
    PresentationOptions,
    SocialOptions,
    VideoOptions,
)


def test_generation_config_shared_defaults() -> None:
    """Verify standard defaults for shared editorial posture."""
    config = GenerationConfig()
    assert config.audience == "Executive"
    assert config.tone == "Objective"
    assert config.language == "en"
    assert config.detail_level == DetailLevel.STANDARD
    assert config.objective == CommunicationObjective.INFORM
    assert config.style == ContentStyle.CORPORATE


def test_generation_config_output_specific_options_resolution() -> None:
    """Verify output-specific options can be supplied without duplicating shared fields."""
    config = GenerationConfig(
        audience="C-Suite",
        tone="Authoritative",
        objective=CommunicationObjective.ALERT,
        presentation=PresentationOptions(
            slide_count=15,
            aspect_ratio="16:9",
            theme="dark_minimal",
            include_speaker_notes=True,
        ),
        video=VideoOptions(
            target_duration_sec=120,
            voice_profile="executive_female",
            pacing="fast",
        ),
        document=DocumentOptions(
            doc_format=".pdf",
            include_executive_summary=True,
            citation_style="author-year",
        ),
        social=SocialOptions(
            platform="twitter",
            thread_mode=True,
            include_hashtags=False,
            max_length=280,
        ),
        infographic=InfographicOptions(
            layout="horizontal",
            color_palette="financial_amber",
            density="compact",
        ),
    )

    # 1. Verify shared fields are not duplicated inside output options
    assert not hasattr(config.presentation, "audience")
    assert not hasattr(config.video, "tone")
    assert not hasattr(config.document, "objective")

    # 2. Verify typed options resolution via helper
    pres_opts = config.get_options_for_format(OutputFormat.PRESENTATION)
    assert isinstance(pres_opts, PresentationOptions)
    assert pres_opts.slide_count == 15
    assert pres_opts.theme == "dark_minimal"

    video_opts = config.get_options_for_format(OutputFormat.VIDEO)
    assert isinstance(video_opts, VideoOptions)
    assert video_opts.target_duration_sec == 120

    doc_opts = config.get_options_for_format(OutputFormat.SUMMARY)
    assert isinstance(doc_opts, DocumentOptions)
    assert doc_opts.doc_format == ".pdf"

    social_opts = config.get_options_for_format(OutputFormat.LINKEDIN)
    assert isinstance(social_opts, SocialOptions)
    assert social_opts.platform == "twitter"

    info_opts = config.get_options_for_format(OutputFormat.INFOGRAPHIC)
    assert isinstance(info_opts, InfographicOptions)
    assert info_opts.layout == "horizontal"


def test_generation_config_default_fallback_for_unconfigured_formats() -> None:
    """Verify helper returns sensible defaults when output-specific config is None."""
    config = GenerationConfig(audience="Engineers", tone="Technical")

    # Presentation was not explicitly set -> returns sensible PresentationOptions defaults
    pres_opts = config.get_options_for_format(OutputFormat.PRESENTATION)
    assert isinstance(pres_opts, PresentationOptions)
    assert pres_opts.slide_count == 10
    assert pres_opts.aspect_ratio == "16:9"

    # Video defaults
    video_opts = config.get_options_for_format(OutputFormat.VIDEO)
    assert isinstance(video_opts, VideoOptions)
    assert video_opts.target_duration_sec == 60
