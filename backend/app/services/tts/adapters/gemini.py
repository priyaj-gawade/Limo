"""Gemini Neural TTS Adapter (Phase D8.3 & Google Gemini Pro).

Integrates Google's native Gemini TTS models (gemini-3.8-flash-tts / gemini-2.5-flash-preview-tts)
into Limo's multi-provider voice and deliverable pipeline.
Uses available Gemini API keys with multi-key rotation and zero external dependencies.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import wave

from ....config import settings
from ..base import BaseTTSProvider, compute_audio_sha256, probe_audio_duration
from ..models import (
    TTSProviderUnavailableError,
    TTSRequest,
    TTSResult,
    TTSSynthesisError,
    VoiceMetadata,
)

logger = logging.getLogger("limo.services.tts.adapters.gemini")


class GeminiTTSAdapter(BaseTTSProvider):
    """Primary TTS provider powered by Google Gemini Neural Speech."""

    id = "gemini"
    name = "Gemini Neural TTS"
    is_primary = True

    _CURATED_VOICES: List[VoiceMetadata] = [
        VoiceMetadata(
            provider="gemini",
            voice_id="Aoede",
            display_name="Aoede (Gemini)",
            language="en-US",
            gender="Female",
            description="Deep, measured, and expressive neural voice",
            is_default=True,
            is_primary=True,
        ),
        VoiceMetadata(
            provider="gemini",
            voice_id="Puck",
            display_name="Puck (Gemini)",
            language="en-US",
            gender="Male",
            description="Conversational, lively, and engaging tone",
            is_primary=True,
        ),
        VoiceMetadata(
            provider="gemini",
            voice_id="Charon",
            display_name="Charon (Gemini)",
            language="en-US",
            gender="Male",
            description="Warm, calm, and authoritative narration",
            is_primary=True,
        ),
        VoiceMetadata(
            provider="gemini",
            voice_id="Fenrir",
            display_name="Fenrir (Gemini)",
            language="en-US",
            gender="Male",
            description="Rich, confident, and direct tone",
            is_primary=True,
        ),
        VoiceMetadata(
            provider="gemini",
            voice_id="Kore",
            display_name="Kore (Gemini)",
            language="en-US",
            gender="Female",
            description="Clear, gentle, and articulated delivery",
            is_primary=True,
        ),
    ]

    def _get_api_keys(self) -> List[str]:
        """Collect available non-empty Gemini keys for rotation."""
        keys: List[str] = []
        for cand in [
            getattr(settings, "gemini_key_1", None),
            getattr(settings, "gemini_key_2", None),
            getattr(settings, "gemini_key_3", None),
            getattr(settings, "gemini_api_key", None),
            os.environ.get("GEMINI_KEY_1"),
            os.environ.get("GEMINI_KEY_2"),
            os.environ.get("GEMINI_KEY_3"),
            os.environ.get("GEMINI_API_KEY"),
        ]:
            if cand and str(cand).strip() and str(cand).strip() not in keys:
                keys.append(str(cand).strip())
        return keys

    def get_status(self) -> bool:
        """True if google-genai is installed and at least one API key is present."""
        try:
            from google import genai  # noqa: F401
            return len(self._get_api_keys()) > 0
        except Exception:
            return False

    def list_voices(self) -> List[VoiceMetadata]:
        available = self.get_status()
        return [
            v.model_copy(update={"is_available": available})
            for v in self._CURATED_VOICES
        ]

    def synthesize(self, request: TTSRequest) -> TTSResult:
        if not self.get_status():
            raise TTSProviderUnavailableError(
                "Gemini TTS is unavailable: No Gemini API keys configured or google-genai not installed."
            )

        keys = self._get_api_keys()
        if not keys:
            raise TTSProviderUnavailableError("No valid Gemini API key found for Gemini TTS.")

        try:
            from google import genai
            from google.genai import types
        except ImportError as e:
            raise TTSProviderUnavailableError(f"google-genai package missing: {e}")

        voice_id = self.resolve_voice_id(request.voice)
        valid_ids = [v.voice_id for v in self._CURATED_VOICES]
        if voice_id not in valid_ids:
            # Map or fallback to default
            voice_id = "Aoede"

        output_path = request.output_path or Path(f"gemini_tts_{int(time.time() * 1000)}.wav")
        output_path = output_path.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Candidate models in priority order
        model_candidates = ["gemini-3.8-flash-tts", "gemini-2.5-flash-preview-tts"]
        last_err: Optional[Exception] = None
        audio_bytes: Optional[bytes] = None
        mime_type = "audio/wav"

        for key in keys:
            client = genai.Client(api_key=key)
            for model_name in model_candidates:
                try:
                    logger.info("Attempting Gemini TTS with model '%s', voice '%s'", model_name, voice_id)
                    config = types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=voice_id
                                )
                            )
                        ),
                    )
                    resp = client.models.generate_content(
                        model=model_name,
                        contents=request.text.strip(),
                        config=config,
                    )
                    if not resp.candidates or not resp.candidates[0].content or not resp.candidates[0].content.parts:
                        raise TTSSynthesisError("Gemini TTS returned empty content parts.")

                    part = resp.candidates[0].content.parts[0]
                    if not hasattr(part, "inline_data") or not part.inline_data or not part.inline_data.data:
                        raise TTSSynthesisError("Gemini TTS response missing inline audio data.")

                    audio_bytes = part.inline_data.data
                    mime_type = part.inline_data.mime_type or "audio/wav"
                    break
                except Exception as e:
                    last_err = e
                    logger.warning("Gemini TTS attempt with model %s failed: %s", model_name, e)
                    continue

            if audio_bytes is not None:
                break

        if audio_bytes is None:
            raise TTSSynthesisError(f"Gemini TTS synthesis failed across all keys/models: {last_err}")

        # Write audio data to output file (wrapping raw PCM in standard WAV if required)
        try:
            if "pcm" in mime_type.lower() or mime_type.startswith("audio/L16"):
                with wave.open(str(output_path), "wb") as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(24000)
                    wav_file.writeframes(audio_bytes)
                final_mime = "audio/wav"
            else:
                output_path.write_bytes(audio_bytes)
                final_mime = mime_type
        except Exception as e:
            raise TTSSynthesisError(f"Failed to persist synthesized Gemini audio: {e}")

        file_size = output_path.stat().st_size
        sha = compute_audio_sha256(output_path)
        duration = probe_audio_duration(output_path)

        return TTSResult(
            output_path=output_path,
            mime_type=final_mime,
            size_bytes=file_size,
            duration_seconds=duration,
            sha256=sha,
            provider=self.id,
            voice_id=voice_id,
            metadata={"model": model_candidates[0], "gemini_voice": voice_id},
        )
