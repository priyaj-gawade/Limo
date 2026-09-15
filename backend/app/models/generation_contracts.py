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


class VideoVoiceConfig(LimoBaseModel):
    """Per-job TTS audio narration configuration."""
    provider: str = Field(default="edge_tts", description="TTS audio engine provider (edge_tts)")
    voice_id: str = Field(default="en-US-AndrewMultilingualNeural", description="Specific voice identifier")
    speed: float = Field(default=1.0, ge=0.5, le=2.0, description="Narration playback speed multiplier")
    pitch: float = Field(default=0.0, ge=-50.0, le=50.0, description="Voice pitch adjustment in Hz or semitones")


class VideoScriptSection(LimoBaseModel):
    """Discrete timeline section or scene for video generation."""
    section_id: str = Field(description="Unique scene/section identifier")
    heading: str = Field(default="", description="Section heading or theme")
    content: str = Field(description="Spoken narration content")
    visual_hint: str = Field(default="", description="Visual keyword or prompt for asset acquisition")
    duration_seconds: Optional[float] = Field(default=None, description="Optional scene duration constraint")


class CaptionUnit(LimoBaseModel):
    """Discrete, timed caption display unit adhering to the <=3-word hard rule (Phase D8.4)."""
    text: str = Field(description="Spoken caption text (at most 3 words)")
    start_time: float = Field(ge=0.0, description="Start timestamp in seconds")
    end_time: float = Field(ge=0.0, description="End timestamp in seconds")
    treatment: Literal["drop", "rail", "embed"] = Field(default="rail", description="Caption treatment doctrine")
    emphasis: List[str] = Field(default_factory=list, description="Keywords for inline emphasis")
    scene_id: Optional[str] = Field(default=None, description="Originating scene ID")
    timing_source: str = Field(default="phrase_proportional", description="Timing provenance")

    @field_validator("text")
    @classmethod
    def validate_word_limit(cls, v: str) -> str:
        words = v.strip().split()
        if len(words) > 3:
            raise ValueError(f"Caption display unit must contain at most 3 words, got {len(words)}: '{v}'")
        if len(words) == 0:
            raise ValueError("Caption display unit cannot be empty")
        return v


def validate_caption_word_limit(captions: List[CaptionUnit]) -> None:
    """Validate that every visible caption unit contains AT MOST 3 words.

    Raises ValueError if any caption unit exceeds 3 words or has invalid duration.
    """
    for idx, cue in enumerate(captions):
        if cue.treatment == "drop":
            continue
        words = cue.text.strip().split()
        if len(words) > 3:
            raise ValueError(
                f"Caption word limit violation at caption {idx} ({cue.start_time:.2f}s - {cue.end_time:.2f}s): "
                f"expected at most 3 words, got {len(words)} words: '{cue.text}'"
            )
        if len(words) == 0:
            raise ValueError(f"Caption {idx} has empty text.")
        if cue.end_time < cue.start_time:
            raise ValueError(f"Caption {idx} has invalid duration: start={cue.start_time:.3f}s, end={cue.end_time:.3f}s")



class VideoBrief(LimoBaseModel):
    """Sanitized creative specification produced by Limo for the OpenMontage Director Agent.

    CRITICAL ARCHITECTURAL BOUNDARY:
    This model intentionally excludes raw user directives or commands.
    It contains only sanitized creative parameters, preventing narration leakage at the root.
    """
    topic: str = Field(description="Sanitized subject or theme, free of commands (e.g. 'Deep Space Exploration')")
    target_duration_seconds: float = Field(default=30.0, ge=8.0, le=300.0, description="Target video runtime in seconds")
    aspect_ratio: str = Field(default="16:9", description="Video format ('16:9', '9:16', '1:1')")
    audience: str = Field(default="general audience", description="Target viewer demographic")
    tone: str = Field(default="inspirational, educational", description="Narrative delivery tone")
    language: str = Field(default="en", description="Narration language code")
    key_points: List[str] = Field(default_factory=list, description="Sanitized bullet points to guide scene narrative")
    voice_config: VideoVoiceConfig = Field(default_factory=VideoVoiceConfig, description="TTS voice parameters")


class VideoGenerationContract(LimoBaseModel):
    """Authoritative contract passed across subprocess boundary to OpenMontage runner."""
    job_id: str = Field(description="Unique sanitized job identifier")
    title: str = Field(description="Deliverable video title")
    conversation_id: Optional[str] = Field(default=None, description="Originating chat session or conversation ID")
    topic: Optional[str] = Field(default=None, description="Core topic or narrative premise")
    target_duration_seconds: float = Field(default=30.0, ge=8.0, le=300.0, description="Target video runtime in seconds")
    aspect_ratio: str = Field(default="16:9", description="Video format ('16:9', '9:16', '1:1')")
    style_playbook: str = Field(default="clean-professional", description="Visual style template")
    render_runtime: str = Field(default="ffmpeg", description="Rendering composition engine")
    voice_config: VideoVoiceConfig = Field(default_factory=VideoVoiceConfig, description="TTS voice parameters")
    subtitles: bool = Field(default=True, description="Whether subtitles are generated")
    script_sections: List[VideoScriptSection] = Field(default_factory=list, description="Pre-planned script sections")
    brief: Optional[VideoBrief] = Field(default=None, description="Sanitized creative Video Brief")
    user_directive: Optional[str] = Field(default=None, description="Raw input directive kept strictly for job provenance outside creative prompt")
    options: Dict[str, Any] = Field(default_factory=dict, description="Stock provider and engine options")


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
