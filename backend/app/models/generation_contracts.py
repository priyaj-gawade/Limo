"""Generation contract schemas and payload specifications (Phase D6.3).

Defines strongly-typed execution payloads for:
- GenOffice Electron Main Automation (Phase D7): POST /api/v1/generate contract
- Video Engine (Phase D8): Versioned contract designed for the future D8 adapter
- Native Text & Social Deliverables: Structured thread & item payloads
"""

from typing import Any, Dict, List, Literal, Optional
from pydantic import Field, field_validator

from .base import LimoBaseModel


class GenOfficeOptions(LimoBaseModel):
    """Configuration options accompanying a GenOffice document generation request."""
    title: str = Field(description="Deliverable title")
    approx_pages: Optional[int] = Field(default=None, ge=1, le=100, description="Target page count or slide count")
    theme: Optional[str] = Field(default="slate_corporate", description="Visual theme identifier")
    audience: Optional[str] = Field(default="Executive", description="Target audience profile")
    tone: Optional[str] = Field(default="professional", description="Editorial tone")
    detail_level: Optional[str] = Field(default="standard", description="Granularity level")
    save_directory: Optional[str] = Field(default=None, description="Optional target directory for generated file")
    canonical_id: str = Field(description="ID of originating CanonicalContent")
    canonical_hash: str = Field(min_length=64, max_length=64, description="Cryptographic hash of CanonicalContent")
    sections_outline: List[str] = Field(default_factory=list, description="Ordered section or slide headings")
    custom_metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary engine parameters")


class GenOfficePayload(LimoBaseModel):
    """Structured generation contract for GenOffice Electron Main (POST /api/v1/generate)."""
    type: Literal["document", "presentation", "spreadsheet", "pdf", "markdown", "html", "advisory", "summary"] = Field(
        description="Target document type"
    )
    prompt: str = Field(description="Grounded instruction synthesizing intent and canonical context")
    project_id: Optional[str] = Field(default=None, description="Associated project ID")
    session_id: Optional[str] = Field(default=None, description="Active chat session ID")
    options: GenOfficeOptions = Field(description="Detailed document options and canonical extract")


class VideoScriptScene(LimoBaseModel):
    """Discrete timeline scene or narration segment within a video generation blueprint."""
    scene_index: int = Field(ge=1, description="1-indexed scene sequence number")
    visual_cue: str = Field(description="Description of visual elements, graphics, or b-roll to display")
    narration_text: str = Field(description="Spoken narration text derived from canonical facts/events")
    estimated_duration_seconds: int = Field(ge=1, le=300, description="Estimated duration of scene in seconds")


class VideoEnginePayload(LimoBaseModel):
    """Versioned contract designed for the future D8 video engine adapter (OpenMontage + MPT)."""
    title: str = Field(description="Working title of the video deliverable")
    script_blueprint: List[VideoScriptScene] = Field(min_length=1, description="Ordered scenes and narration script")
    audio_config: Dict[str, Any] = Field(
        default_factory=lambda: {"voice_profile": "professional_neutral", "speech_rate": 1.0, "language": "en"},
        description="Narration and TTS audio configuration",
    )
    visual_config: Dict[str, Any] = Field(
        default_factory=lambda: {"aspect_ratio": "16:9", "visual_style": "corporate_clean", "subtitles": True},
        description="Video aspect ratio and visual styling options",
    )
    estimated_duration_seconds: int = Field(ge=5, le=1800, description="Total planned video runtime in seconds")
    canonical_id: str = Field(description="Originating CanonicalContent ID")
    canonical_hash: str = Field(min_length=64, max_length=64, description="Cryptographic SHA-256 hash of CanonicalContent")


class TweetItem(LimoBaseModel):
    """Single tweet within an X/Twitter thread, strictly bounded to 280 characters."""
    tweet_number: int = Field(ge=1, description="Monotonic sequence number within the thread (1/N)")
    text: str = Field(min_length=1, max_length=280, description="Post content strictly <= 280 characters")
    char_count: int = Field(ge=1, le=280, description="Verified character length of text")

    @field_validator("char_count")
    @classmethod
    def validate_char_count_matches(cls, v: int, info) -> int:
        text = info.data.get("text")
        if text is not None and len(text) != v:
            raise ValueError(f"char_count {v} does not match len(text) {len(text)}")
        return v


class TwitterThreadPayload(LimoBaseModel):
    """Structured collection of tweets constituting a complete X/Twitter thread deliverable."""
    topic: str = Field(description="Thread subject or theme")
    tweets: List[TweetItem] = Field(min_length=1, description="Ordered tweets forming the thread")
    total_tweets: int = Field(ge=1, description="Total number of tweets in the thread")
