"""Azure AI Speech TTS Provider Adapter (Phase D8.3)."""

import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape, quoteattr
import requests

from ..base import BaseTTSProvider, compute_audio_sha256, probe_audio_duration
from ..models import (
    TTSProviderUnavailableError,
    TTSRequest,
    TTSResult,
    TTSSynthesisError,
    VoiceMetadata,
)

_MP3_FORMAT = "audio-48khz-192kbitrate-mono-mp3"
_WAV_FORMAT = "riff-48khz-16bit-mono-pcm"


class AzureTTSAdapter(BaseTTSProvider):
    """Primary Cloud TTS Provider powered by Azure AI Speech REST endpoint."""

    id = "azure"
    name = "Azure AI Speech"
    is_primary = True

    _CURATED_VOICES: List[VoiceMetadata] = [
        VoiceMetadata(
            provider="azure",
            voice_id="en-US-AndrewMultilingualNeural",
            display_name="Andrew",
            language="en-US",
            gender="Male",
            description="Warm, confident, conversational founder tone",
            is_default=True,
            is_primary=True,
        ),
        VoiceMetadata(
            provider="azure",
            voice_id="en-US-AvaMultilingualNeural",
            display_name="Ava",
            language="en-US",
            gender="Female",
            description="Confident, bright, modern narrative voice",
            is_primary=True,
        ),
        VoiceMetadata(
            provider="azure",
            voice_id="en-US-BrandonMultilingualNeural",
            display_name="Brandon",
            language="en-US",
            gender="Male",
            description="Deeper, measured, authoritative presentation style",
            is_primary=True,
        ),
        VoiceMetadata(
            provider="azure",
            voice_id="en-US-GuyNeural",
            display_name="Guy",
            language="en-US",
            gender="Male",
            description="Professional, authoritative broadcast delivery",
            is_primary=True,
        ),
        VoiceMetadata(
            provider="azure",
            voice_id="en-US-JennyNeural",
            display_name="Jenny",
            language="en-US",
            gender="Female",
            description="Friendly, articulate, versatile delivery",
            is_primary=True,
        ),
    ]

    def get_status(self) -> bool:
        """True if AZURE_SPEECH_KEY and region/endpoint are configured in environment."""
        key = os.environ.get("AZURE_SPEECH_KEY")
        region = os.environ.get("AZURE_SPEECH_REGION") or os.environ.get("AZURE_TTS_ENDPOINT")
        return bool(key and region)

    def list_voices(self) -> List[VoiceMetadata]:
        available = self.get_status()
        return [
            v.model_copy(update={"is_available": available})
            for v in self._CURATED_VOICES
        ]

    def _host(self) -> str:
        endpoint = os.environ.get("AZURE_TTS_ENDPOINT")
        if endpoint:
            return endpoint.rstrip("/")
        region = os.environ.get("AZURE_SPEECH_REGION", "eastus").strip()
        return f"https://{region}.tts.speech.microsoft.com"

    def _build_ssml(self, text: str, voice_id: str, speed: float, options: Dict[str, Any]) -> str:
        locale = str(options.get("locale", "en-US"))
        rate_val = options.get("rate")
        if not rate_val:
            pct = round((speed - 1.0) * 100)
            rate_val = f"{pct:+d}%" if pct else "0%"

        pitch_val = str(options.get("pitch", "0%"))
        style = options.get("style")

        safe_text = escape(text)
        inner = f"<prosody rate={quoteattr(str(rate_val))} pitch={quoteattr(pitch_val)}>{safe_text}</prosody>"
        if style:
            inner = f"<mstts:express-as style={quoteattr(str(style))}>{inner}</mstts:express-as>"

        return (
            f'<speak version="1.0" '
            f'xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xmlns:mstts="https://www.w3.org/2001/mstts" '
            f"xml:lang={quoteattr(locale)}>"
            f"<voice name={quoteattr(voice_id)}>{inner}</voice></speak>"
        )

    def synthesize(self, request: TTSRequest) -> TTSResult:
        if not self.get_status():
            raise TTSProviderUnavailableError(
                "Azure AI Speech credentials not configured. "
                "Set AZURE_SPEECH_KEY and AZURE_SPEECH_REGION environment variables."
            )

        voice_id = self.resolve_voice_id(request.voice)
        api_key = os.environ["AZURE_SPEECH_KEY"]
        container = (request.output_format or "mp3").lower()
        azure_format = _WAV_FORMAT if container == "wav" else _MP3_FORMAT
        mime_type = "audio/wav" if container == "wav" else "audio/mpeg"

        output_path = request.output_path or Path(f"azure_tts_{int(time.time())}.{container}")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        ssml = self._build_ssml(request.text, voice_id, request.speed, request.provider_options)
        url = f"{self._host()}/cognitiveservices/v1"
        headers = {
            "Ocp-Apim-Subscription-Key": api_key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": azure_format,
            "User-Agent": "Limo-TTS-Engine/1.0",
        }

        try:
            res = requests.post(url, headers=headers, data=ssml.encode("utf-8"), timeout=30)
            if res.status_code != 200:
                raise TTSSynthesisError(f"Azure Speech API returned error {res.status_code}: {res.text}")
            with open(output_path, "wb") as f:
                f.write(res.content)
        except Exception as e:
            if isinstance(e, TTSSynthesisError):
                raise
            raise TTSSynthesisError(f"Failed to connect to Azure Speech endpoint: {e}") from e

        size_bytes = output_path.stat().st_size
        if size_bytes == 0:
            raise TTSSynthesisError(f"Generated Azure audio file is empty: {output_path}")

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
            metadata={"format": container, "speed": request.speed},
        )
