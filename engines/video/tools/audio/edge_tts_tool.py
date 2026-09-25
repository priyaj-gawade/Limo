"""Microsoft Edge Text-to-Speech provider tool.

High-quality neural speech with zero API key required, supporting 300+ voices
across 70+ languages through Microsoft Edge TTS service.
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)


class EdgeTTSTool(BaseTool):
    name = "edge_tts"
    version = "0.1.0"
    tier = ToolTier.VOICE
    capability = "tts"
    provider = "edge_tts"
    stability = ToolStability.PRODUCTION
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.API

    dependencies = []
    install_instructions = "Install edge-tts: pip install edge-tts"
    fallback = "google_tts"
    fallback_tools = ["google_tts", "openai_tts", "piper_tts"]
    agent_skills = ["text-to-speech"]

    capabilities = [
        "text_to_speech",
        "voice_selection",
        "multilingual",
    ]
    supports = {
        "voice_cloning": False,
        "multilingual": True,
        "offline": False,
        "native_audio": True,
        "ssml": False,
    }
    best_for = [
        "free high-quality neural text-to-speech without API key",
        "explainer narration with natural cadence",
        "fast local development and production fallback",
    ]
    not_good_for = [
        "voice cloning",
        "fully offline environments without internet",
    ]

    input_schema = {
        "type": "object",
        "required": ["text"],
        "properties": {
            "text": {"type": "string", "description": "Text to convert to speech"},
            "voice": {
                "type": "string",
                "default": "en-US-AndrewMultilingualNeural",
                "description": (
                    "Voice name. Examples: en-US-AndrewMultilingualNeural, "
                    "en-US-AvaNeural, en-US-BrianNeural, en-US-EmmaNeural, "
                    "en-GB-SoniaNeural"
                ),
            },
            "voice_id": {
                "type": "string",
                "description": "Alias for voice name.",
            },
            "rate": {
                "type": "string",
                "default": "+0%",
                "description": "Speaking rate adjustment, e.g. '+10%' or '-10%'",
            },
            "speaking_rate": {
                "type": "number",
                "default": 1.0,
                "description": "Speaking speed multiplier (1.0 = normal, 1.2 = +20%)",
            },
            "pitch": {
                "type": "string",
                "default": "+0Hz",
                "description": "Pitch adjustment, e.g. '+5Hz' or '-5Hz'",
            },
            "volume": {
                "type": "string",
                "default": "+0%",
                "description": "Volume adjustment, e.g. '+0%' or '-20%'",
            },
            "output_path": {
                "type": "string",
                "description": "Path to write the output MP3 file",
            },
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=256, vram_mb=0, disk_mb=50, network_required=True
    )
    retry_policy = RetryPolicy(
        max_retries=2, retryable_errors=["timeout", "connection_error"]
    )
    idempotency_key_fields = ["text", "voice", "rate", "pitch"]
    side_effects = ["writes audio file to output_path"]
    user_visible_verification = ["Listen to generated audio for speech quality"]

    def get_status(self) -> ToolStatus:
        try:
            import edge_tts  # noqa: F401
            return ToolStatus.AVAILABLE
        except ImportError:
            return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        try:
            import edge_tts
        except ImportError:
            return ToolResult(
                success=False,
                error="edge-tts is not installed. Run: pip install edge-tts",
            )

        text = (inputs.get("text") or "").strip()
        if not text:
            return ToolResult(success=False, error="Input text is required and cannot be empty.")

        voice = (
            inputs.get("voice")
            or inputs.get("voice_id")
            or "en-US-AndrewMultilingualNeural"
        )

        # Convert speaking_rate float if rate string not explicitly provided
        rate_raw = inputs.get("rate")
        if isinstance(rate_raw, str) and (rate_raw.endswith("%") or rate_raw.endswith("Hz")):
            rate_str = rate_raw
        elif "speaking_rate" in inputs and isinstance(inputs["speaking_rate"], (int, float)):
            speed = float(inputs["speaking_rate"])
            percent = round((speed - 1.0) * 100)
            rate_str = f"{percent:+d}%"
        else:
            rate_str = "+0%"

        pitch_raw = inputs.get("pitch")
        if isinstance(pitch_raw, (int, float)):
            pitch_str = f"{int(pitch_raw):+d}Hz" if pitch_raw != 0 else "+0Hz"
        elif isinstance(pitch_raw, str) and (pitch_raw.endswith("Hz") or pitch_raw.endswith("%")):
            pitch_str = pitch_raw
        else:
            pitch_str = "+0Hz"

        vol_raw = inputs.get("volume")
        if isinstance(vol_raw, str) and (vol_raw.endswith("%") or vol_raw.endswith("dB")):
            volume_str = vol_raw
        elif isinstance(vol_raw, (int, float)):
            volume_str = f"{int(vol_raw):+d}%"
        else:
            volume_str = "+0%"

        output_path_str = inputs.get("output_path")
        if output_path_str:
            output_path = Path(output_path_str)
        else:
            output_path = Path("output.mp3")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        start_time = time.time()
        try:
            async def _generate() -> None:
                communicate = edge_tts.Communicate(
                    text=text,
                    voice=voice,
                    rate=rate_str,
                    pitch=pitch_str,
                    volume=volume_str,
                )
                await communicate.save(str(output_path))

            asyncio.run(_generate())

            if not output_path.is_file() or output_path.stat().st_size == 0:
                return ToolResult(
                    success=False,
                    error=f"Edge TTS failed: output file is empty or missing: {output_path}",
                )

            duration = round(time.time() - start_time, 2)
            file_size = output_path.stat().st_size

            return ToolResult(
                success=True,
                data={
                    "provider": "edge_tts",
                    "voice": voice,
                    "output": str(output_path),
                    "file_size_bytes": file_size,
                    "duration_seconds": duration,
                    "text_length": len(text),
                },
                artifacts=[str(output_path)],
                duration_seconds=duration,
                cost_usd=0.0,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Edge TTS generation failed: {e}",
            )
