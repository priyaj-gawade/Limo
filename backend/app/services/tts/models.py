"""Data models and exceptions for Limo Text-to-Speech (TTS) & Voice Layer (Phase D8.3)."""

from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class VoiceMetadata(BaseModel):
    """Metadata representing a supported voice across TTS providers."""
    provider: str = Field(description="TTS provider identifier (e.g. 'azure', 'openai', 'piper', 'edge_tts')")
    voice_id: str = Field(description="Unique provider voice identifier")
    display_name: str = Field(description="Human-friendly voice display name (e.g. 'Andrew', 'Alloy')")
    language: str = Field(default="en-US", description="Primary BCP-47 language tag")
    gender: Optional[str] = Field(default=None, description="Gender classification ('Male', 'Female', 'Neutral')")
    description: Optional[str] = Field(default=None, description="Short sonic character description")
    is_default: bool = Field(default=False, description="Whether this is the recommended default voice")
    is_available: bool = Field(default=True, description="Whether the underlying provider is available")
    is_primary: bool = Field(default=True, description="Whether provider is primary (Azure/OpenAI/Piper) or fallback (Edge TTS)")


class TTSRequest(BaseModel):
    """Normalized text-to-speech synthesis request.
    
    Exposes universal common parameters while housing provider-specific options
    in provider_options to avoid pretending all engines share identical features.
    """
    text: str = Field(description="Narration text to synthesize into speech")
    voice: str = Field(description="Selected voice identifier or alias")
    provider: Optional[str] = Field(default=None, description="Explicit provider identifier (if requested)")
    speed: float = Field(default=1.0, ge=0.25, le=4.0, description="Speaking rate multiplier")
    output_format: str = Field(default="mp3", description="Audio container format ('mp3' or 'wav')")
    output_path: Optional[Path] = Field(default=None, description="Target destination file path on disk")
    provider_options: Dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific parameters (e.g. pitch, style, model, instructions, speaker_id)",
    )


class TTSResult(BaseModel):
    """Standardized output metadata produced by real TTS synthesis."""
    output_path: Path = Field(description="Absolute path to generated audio file")
    mime_type: str = Field(default="audio/mpeg", description="MIME container type")
    size_bytes: int = Field(description="Physical file size in bytes")
    duration_seconds: Optional[float] = Field(default=None, description="Probed audio duration in seconds")
    sha256: str = Field(description="Cryptographic SHA-256 digest of generated audio bytes")
    provider: str = Field(description="Provider that performed synthesis")
    voice_id: str = Field(description="Actual voice ID utilized")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary engine provenance metadata")


class TTSException(Exception):
    """Base exception for all Limo TTS errors."""
    pass


class TTSProviderUnavailableError(TTSException):
    """Raised when a requested TTS provider is not configured or reachable."""
    pass


class InvalidVoiceError(TTSException):
    """Raised when an invalid or unknown voice/provider is requested."""
    pass


class TTSSynthesisError(TTSException):
    """Raised when real audio synthesis fails during execution."""
    pass
