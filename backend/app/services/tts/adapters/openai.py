"""OpenAI Speech TTS Provider Adapter (Phase D8.3)."""

import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

from ..base import BaseTTSProvider, compute_audio_sha256, probe_audio_duration
from ..models import (
    TTSProviderUnavailableError,
    TTSRequest,
    TTSResult,
    TTSSynthesisError,
    VoiceMetadata,
)


class OpenAITTSAdapter(BaseTTSProvider):
    """Primary Cloud TTS Provider powered by OpenAI Speech API."""

    id = "openai"
    name = "OpenAI Speech"
    is_primary = True

    _CURATED_VOICES: List[VoiceMetadata] = [
        VoiceMetadata(
            provider="openai",
            voice_id="alloy",
            display_name="Alloy",
            language="en-US",
            gender="Neutral",
            description="Balanced, versatile, neutral tone",
            is_primary=True,
        ),
        VoiceMetadata(
            provider="openai",
            voice_id="echo",
            display_name="Echo",
            language="en-US",
            gender="Male",
            description="Warm, rounded, gentle male voice",
            is_primary=True,
        ),
        VoiceMetadata(
            provider="openai",
            voice_id="fable",
            display_name="Fable",
            language="en-GB",
            gender="Male",
            description="British accent, expressive narrative tone",
            is_primary=True,
        ),
        VoiceMetadata(
            provider="openai",
            voice_id="onyx",
            display_name="Onyx",
            language="en-US",
            gender="Male",
            description="Deep, resonant, authoritative delivery",
            is_primary=True,
        ),
        VoiceMetadata(
            provider="openai",
            voice_id="nova",
            display_name="Nova",
            language="en-US",
            gender="Female",
            description="Energetic, clear, friendly narrative voice",
            is_primary=True,
        ),
        VoiceMetadata(
            provider="openai",
            voice_id="shimmer",
            display_name="Shimmer",
            language="en-US",
            gender="Female",
            description="Bright, crisp, clear female voice",
            is_primary=True,
        ),
    ]

    def get_status(self) -> bool:
        """True if OPENAI_API_KEY is configured in environment."""
        return bool(os.environ.get("OPENAI_API_KEY"))

    def list_voices(self) -> List[VoiceMetadata]:
        available = self.get_status()
        return [
            v.model_copy(update={"is_available": available})
            for v in self._CURATED_VOICES
        ]

    def synthesize(self, request: TTSRequest) -> TTSResult:
        if not self.get_status():
            raise TTSProviderUnavailableError(
                "OpenAI Speech credentials not configured. "
                "Set the OPENAI_API_KEY environment variable."
            )

        try:
            from openai import OpenAI
        except ImportError as e:
            raise TTSProviderUnavailableError("OpenAI Python package not installed") from e

        voice_id = self.resolve_voice_id(request.voice)
        container = (request.output_format or "mp3").lower()
        if container not in ("mp3", "wav", "opus", "aac", "flac"):
            container = "mp3"
        mime_type = "audio/wav" if container == "wav" else "audio/mpeg"

        output_path = request.output_path or Path(f"openai_tts_{int(time.time())}.{container}")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        model = str(request.provider_options.get("model") or "tts-1")
        kwargs: Dict[str, Any] = {
            "model": model,
            "voice": voice_id,
            "input": request.text,
            "response_format": container,
        }
        if request.speed != 1.0:
            kwargs["speed"] = max(0.25, min(4.0, request.speed))
        if request.provider_options.get("instructions"):
            kwargs["instructions"] = request.provider_options["instructions"]

        try:
            client = OpenAI()
            with client.audio.speech.with_streaming_response.create(**kwargs) as response:
                response.stream_to_file(output_path)
        except Exception as e:
            raise TTSSynthesisError(f"OpenAI TTS synthesis failed: {e}") from e

        size_bytes = output_path.stat().st_size
        if size_bytes == 0:
            raise TTSSynthesisError(f"Generated OpenAI audio file is empty: {output_path}")

        duration = probe_audio_duration(output_path)
        sha256 = compute_audio_sha256(output_path)

        return TTSResult(
            output_path=output_path.resolve(),
            mime_type=mime_type,
            size_bytes=size_bytes,
            duration_seconds=duration,
            sha256=sha256,
            provider=self.id,
            voice_id=voice_id,
            metadata={"model": model, "format": container, "speed": request.speed},
        )
