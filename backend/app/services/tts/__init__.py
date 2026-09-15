"""Limo TTS & Voice Layer (Phase D8.3)."""

from .base import BaseTTSProvider
from .models import (
    InvalidVoiceError,
    TTSException,
    TTSProviderUnavailableError,
    TTSRequest,
    TTSResult,
    TTSSynthesisError,
    VoiceMetadata,
)
from .registry import TTSProviderRegistry, tts_registry
from .service import TTSService, tts_service

__all__ = [
    "BaseTTSProvider",
    "InvalidVoiceError",
    "TTSException",
    "TTSProviderUnavailableError",
    "TTSRequest",
    "TTSResult",
    "TTSSynthesisError",
    "VoiceMetadata",
    "TTSProviderRegistry",
    "tts_registry",
    "TTSService",
    "tts_service",
]
