"""Edge TTS Fallback Provider Adapter (Phase D8.3)."""

import asyncio
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


class EdgeTTSAdapter(BaseTTSProvider):
    """Fallback TTS Provider powered by Microsoft Edge Neural Speech without requiring API keys."""

    id = "edge_tts"
    name = "Edge TTS (Neural Fallback)"
    is_primary = False  # Explicit fallback per user review critique #1

    _CURATED_VOICES: List[VoiceMetadata] = [
        VoiceMetadata(
            provider="edge_tts",
            voice_id="en-US-AndrewMultilingualNeural",
            display_name="Andrew (Edge)",
            language="en-US",
            gender="Male",
            description="Neural conversational explainer tone",
            is_default=True,
            is_primary=False,
        ),
        VoiceMetadata(
            provider="edge_tts",
            voice_id="en-US-AvaNeural",
            display_name="Ava (Edge)",
            language="en-US",
            gender="Female",
            description="Expressive, modern neural voice",
            is_primary=False,
        ),
        VoiceMetadata(
            provider="edge_tts",
            voice_id="en-US-BrianNeural",
            display_name="Brian (Edge)",
            language="en-US",
            gender="Male",
            description="Deep, measured, professional voice",
            is_primary=False,
        ),
        VoiceMetadata(
            provider="edge_tts",
            voice_id="en-US-EmmaNeural",
            display_name="Emma (Edge)",
            language="en-US",
            gender="Female",
            description="Clear, friendly, bright tone",
            is_primary=False,
        ),
        VoiceMetadata(
            provider="edge_tts",
            voice_id="en-GB-SoniaNeural",
            display_name="Sonia (Edge)",
            language="en-GB",
            gender="Female",
            description="British accent, professional delivery",
            is_primary=False,
        ),
    ]

    def get_status(self) -> bool:
        """True if the edge_tts package is importable."""
        try:
            import edge_tts
            return True
        except ImportError:
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
                "edge_tts package is not installed. Run 'pip install edge-tts'."
            )

        import edge_tts

        voice_id = self.resolve_voice_id(request.voice)
        container = (request.output_format or "mp3").lower()
        if container != "mp3":
            container = "mp3"
        mime_type = "audio/mpeg"

        output_path = request.output_path or Path(f"edge_tts_{int(time.time())}.mp3")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        rate_val = request.provider_options.get("rate")
        if not rate_val:
            pct = round((request.speed - 1.0) * 100)
            rate_val = f"{pct:+d}%" if pct else "+0%"

        pitch_val = str(request.provider_options.get("pitch", "+0Hz"))

        async def _run_edge_tts() -> None:
            communicate = edge_tts.Communicate(
                text=request.text,
                voice=voice_id,
                rate=rate_val,
                pitch=pitch_val,
            )
            await communicate.save(str(output_path.resolve()))

        def _thread_target() -> None:
            asyncio.run(_run_edge_tts())

        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop is not None and loop.is_running():
                # Running inside an active event loop (e.g. FastAPI / pytest-asyncio)
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(_thread_target)
                    future.result(timeout=60)
            else:
                asyncio.run(_run_edge_tts())
        except Exception as e:
            raise TTSSynthesisError(f"Edge TTS generation failed: {e}") from e

        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise TTSSynthesisError(f"Generated Edge TTS audio file is empty: {output_path}")

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
            metadata={"format": "mp3", "speed": request.speed, "rate": rate_val},
        )
