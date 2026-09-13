"""Generation configuration models for Limo transformation pipelines.

Maintains strict separation between:
- Shared configuration (audience, tone, language, detail level, objective, style)
- Output-specific parameters without duplicating shared fields
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from .base import LimoBaseModel
from .enums import (
    CommunicationObjective,
    ContentStyle,
    DetailLevel,
    OutputFormat,
)


class PresentationOptions(BaseModel):
    """Output-specific parameters for slide decks and presentations."""
    slide_count: int = Field(default=10, ge=1, le=100, description="Target slide count")
    aspect_ratio: str = Field(default="16:9", description="Screen aspect ratio (e.g. '16:9', '4:3')")
    theme: str = Field(default="corporate", description="Visual theme or aesthetic (e.g. 'corporate', 'minimal')")
    include_speaker_notes: bool = Field(default=True, description="Whether to generate per-slide speaker notes")


class VideoOptions(BaseModel):
    """Output-specific parameters for synthesized videos (OpenMontage / MoneyPrinterTurbo)."""
    target_duration_sec: int = Field(default=60, ge=15, le=900, description="Target duration in seconds")
    aspect_ratio: str = Field(default="16:9", description="Video aspect ratio (e.g. '16:9', '9:16')")
    voice_profile: str = Field(default="professional_neutral", description="TTS voice profile identifier")
    pacing: str = Field(default="moderate", description="Speech and scene pacing (e.g. 'fast', 'moderate', 'deliberate')")
    include_subtitles: bool = Field(default=True, description="Whether to render hardcoded subtitles/captions")


class DocumentOptions(BaseModel):
    """Output-specific parameters for structured reports, summaries, and policy briefs."""
    doc_format: str = Field(default=".docx", description="Document file extension (e.g. '.docx', '.pdf', '.md')")
    include_executive_summary: bool = Field(default=True, description="Whether to include a dedicated executive summary")
    citation_style: str = Field(default="numbered", description="Citation formatting style (e.g. 'numbered', 'author-year')")


class SocialOptions(BaseModel):
    """Output-specific parameters for social-first posts (LinkedIn, Twitter/X)."""
    platform: str = Field(default="linkedin", description="Target platform (e.g. 'linkedin', 'twitter')")
    thread_mode: bool = Field(default=False, description="Whether to generate a multi-post thread")
    include_hashtags: bool = Field(default=True, description="Whether to include relevant hashtags")
    max_length: int = Field(default=3000, ge=100, le=10000, description="Maximum character length")


class InfographicOptions(BaseModel):
    """Output-specific parameters for visual infographic diagrams."""
    layout: str = Field(default="vertical", description="Canvas orientation (e.g. 'vertical', 'horizontal', 'square')")
    color_palette: str = Field(default="corporate_blue", description="Color scheme identifier")
    density: str = Field(default="standard", description="Information density (e.g. 'compact', 'standard', 'spacious')")


class SpreadsheetOptions(BaseModel):
    """Output-specific parameters for tabular workbooks (GenOffice Sheets)."""
    include_charts: bool = Field(default=True, description="Whether to include summary charts")
    table_theme: str = Field(default="corporate", description="Table styling theme (e.g. 'corporate', 'modern')")
    freeze_header: bool = Field(default=True, description="Whether to freeze the header row")


class GenerationConfig(LimoBaseModel):
    """Unified transformation configuration defining shared posture and output-specific options."""

    # 1. Shared Editorial Posture
    audience: str = Field(
        default="Executive",
        description="Target stakeholder demographic (e.g. 'Executive', 'Technical', 'Public', 'Policy Makers')"
    )
    tone: str = Field(
        default="Objective",
        description="Communication posture (e.g. 'Authoritative', 'Objective', 'Urgent', 'Engaging')"
    )
    language: str = Field(default="en", description="Target ISO language code (e.g. 'en', 'es', 'hi')")
    detail_level: DetailLevel = Field(
        default=DetailLevel.STANDARD,
        description="Depth of detail and analytical density"
    )
    objective: CommunicationObjective = Field(
        default=CommunicationObjective.INFORM,
        description="Strategic communication intent"
    )
    style: ContentStyle = Field(
        default=ContentStyle.CORPORATE,
        description="Editorial style guidance"
    )

    # 2. Output-Specific Configurations (avoiding shared model duplication)
    presentation: Optional[PresentationOptions] = Field(
        default=None,
        description="Deliverable-specific parameters for slide decks"
    )
    video: Optional[VideoOptions] = Field(
        default=None,
        description="Deliverable-specific parameters for video generation"
    )
    document: Optional[DocumentOptions] = Field(
        default=None,
        description="Deliverable-specific parameters for reports and summaries"
    )
    spreadsheet: Optional[SpreadsheetOptions] = Field(
        default=None,
        description="Deliverable-specific parameters for spreadsheets"
    )
    social: Optional[SocialOptions] = Field(
        default=None,
        description="Deliverable-specific parameters for social posts"
    )
    infographic: Optional[InfographicOptions] = Field(
        default=None,
        description="Deliverable-specific parameters for infographics"
    )

    # 3. Generic/arbitrary forward-compatible overrides
    format_overrides: Dict[str, Any] = Field(
        default_factory=dict,
        description="Deliverable-specific parameter overrides"
    )

    def get_options_for_format(self, fmt: OutputFormat) -> BaseModel:
        """Resolve typed options for a specific OutputFormat with standard defaults."""
        if fmt == OutputFormat.PRESENTATION:
            return self.presentation or PresentationOptions()
        if fmt == OutputFormat.VIDEO:
            return self.video or VideoOptions()
        if fmt in (
            OutputFormat.DOCUMENT,
            OutputFormat.SUMMARY,
            OutputFormat.ADVISORY,
            OutputFormat.MARKDOWN,
            OutputFormat.HTML,
            OutputFormat.PDF,
        ):
            return self.document or DocumentOptions()
        if fmt == OutputFormat.SPREADSHEET:
            return self.spreadsheet or SpreadsheetOptions()
        if fmt in (OutputFormat.LINKEDIN, OutputFormat.TWITTER):
            return self.social or SocialOptions()
        if fmt == OutputFormat.INFOGRAPHIC:
            return self.infographic or InfographicOptions()
        return BaseModel()
