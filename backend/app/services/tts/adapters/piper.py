"""Piper Local Offline TTS Provider Adapter (Phase D8.3)."""

from pathlib import Path
import shutil
import subprocess
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


class PiperTTSAdapter(BaseTTSProvider):
    """Primary Offline TTS Provider running locally via the Piper neural engine."""

    id = "piper"
    name = "Piper (Offline Neural)"
    is_primary = True

    _CURATED_VOICES: List[VoiceMetadata] = [
        VoiceMetadata(
            provider="piper",
            voice_id="en_US-lessac-medium",
            display_name="Lessac",
            language="en-US",
            gender="Female",
            description="Clear, clean, articulate offline voice",
            is_primary=True,
        ),
        VoiceMetadata(
            provider="piper",
            voice_id="en_US-libritts-high",
            display_name="LibriTTS",
            language="en-US",
            gender="Male",
            description="Expressive, high-definition male narration",
            is_primary=True,
        ),
        VoiceMetadata(
            provider="piper",
            voice_id="en_US-ryan-medium",
            display_name="Ryan",
            language="en-US",
            gender="Male",
            description="Standard conversational offline male voice",
            is_primary=True,
        ),
    ]

    def get_status(self) -> bool:
        """True if the piper binary is present in system PATH."""
        return bool(shutil.which("piper"))

    def list_voices(self) -> List[VoiceMetadata]:
        available = self.get_status()
        return [
            v.model_copy(update={"is_available": available})
            for v in self._CURATED_VOICES
        ]

    def synthesize(self, request: TTSRequest) -> TTSResult:
        if not self.get_status():
            raise TTSProviderUnavailableError(
                "Piper binary is not installed or not found on system PATH. "
                "Install via 'pip install piper-tts' or download binary."
            )

        voice_id = self.resolve_voice_id(request.voice)
        container = "wav"  # Piper natively outputs uncompressed WAV
        mime_type = "audio/wav"

        output_path = request.output_path or Path(f"piper_tts_{int(time.time())}.wav")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        speaker_id = int(request.provider_options.get("speaker_id", 0))
        length_scale = float(request.provider_options.get("length_scale", 1.0 / max(0.25, request.speed)))
        sentence_silence = float(request.provider_options.get("sentence_silence", 0.3))

        cmd = [
            "piper",
            "--model", voice_id,
            "--speaker", str(speaker_id),
            "--length-scale", str(length_scale),
            "--sentence-silence", str(sentence_silence),
            "--output_file", str(output_path.resolve()),
        ]

        try:
            proc = subprocess.run(
                cmd,
                input=request.text,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if proc.returncode != 0:
                raise TTSSynthesisError(f"Piper execution failed (exit {proc.returncode}): {proc.stderr}")
        except Exception as e:
            if isinstance(e, TTSSynthesisError):
                raise
            raise TTSSynthesisError(f"Failed to execute Piper CLI: {e}") from e

        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise TTSSynthesisError(f"Generated Piper audio file is missing or empty: {output_path}")

        size_bytes = output_path.stat().st_size
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
            metadata={"format": "wav", "speaker_id": speaker_id, "speed": request.speed},
        )
