"""Google Gemini Neural Text-to-Speech provider tool.

High-quality expressive neural speech powered by Google Gemini TTS models.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
import wave
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


class GeminiTTSTool(BaseTool):
    name = "gemini_tts"
    version = "0.1.0"
    tier = ToolTier.VOICE
    capability = "tts"
    provider = "gemini"
    stability = ToolStability.PRODUCTION
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.API

    dependencies = []
    install_instructions = "Set GEMINI_API_KEY or GOOGLE_API_KEY environment variable"
    fallback = "edge_tts"
    fallback_tools = ["edge_tts", "piper_tts"]
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
        "high-quality Google Gemini Neural TTS narration",
        "expressive cinematic video narration",
        "fast reliable cloud TTS with multi-key rotation",
    ]
    not_good_for = [
        "voice cloning",
        "fully offline production without internet",
    ]

    input_schema = {
        "type": "object",
        "required": ["text"],
        "properties": {
            "text": {"type": "string", "description": "Text to convert to speech"},
            "voice": {
                "type": "string",
                "default": "Aoede",
                "description": "Voice name (Aoede, Puck, Charon, Fenrir, Kore)",
            },
            "voice_id": {
                "type": "string",
                "description": "Alias for voice name",
            },
            "rate": {
                "type": "string",
                "default": "+0%",
                "description": "Speaking rate adjustment",
            },
            "speaking_rate": {
                "type": "number",
                "default": 1.0,
                "description": "Speaking speed multiplier",
            },
            "pitch": {
                "type": "string",
                "default": "+0Hz",
                "description": "Pitch adjustment",
            },
            "output_path": {
                "type": "string",
                "description": "Path to write the output audio file",
            },
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=256, vram_mb=0, disk_mb=50, network_required=True
    )
    retry_policy = RetryPolicy(
        max_retries=2, retryable_errors=["timeout", "connection_error", "rate_limit"]
    )
    idempotency_key_fields = ["text", "voice"]
    side_effects = ["writes audio file to output_path"]
    user_visible_verification = ["Listen to generated audio for speech quality"]

    @staticmethod
    def _get_api_keys() -> list[str]:
        keys = []
        key_vars = [
            "GEMINI_KEY_1",
            "GEMINI_KEY_2",
            "GEMINI_KEY_3",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
        ]
        for env_var in key_vars:
            val = os.environ.get(env_var)
            if val and val.strip() and val.strip() not in keys:
                keys.append(val.strip())

        if not keys:
            # Check for .env file in parent directories
            for parent in Path(__file__).resolve().parents:
                env_file = parent / ".env"
                if env_file.is_file():
                    with open(env_file, encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            line = line.strip()
                            if not line or line.startswith("#") or "=" not in line:
                                continue
                            k, _, v = line.partition("=")
                            k, v = k.strip(), v.strip().strip("'\"")
                            if k in key_vars and v and v not in keys:
                                keys.append(v)
                    if keys:
                        break
        return keys

    def get_status(self) -> ToolStatus:
        try:
            from google import genai  # noqa: F401
            if self._get_api_keys():
                return ToolStatus.AVAILABLE
            return ToolStatus.UNAVAILABLE
        except ImportError:
            return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        text = (inputs.get("text") or "").strip()
        if not text:
            return ToolResult(success=False, error="Input text is required and cannot be empty.")

        raw_voice = inputs.get("voice") or inputs.get("voice_id") or "Aoede"
        valid_voices = {"Aoede", "Puck", "Charon", "Fenrir", "Kore"}
        voice = raw_voice if raw_voice in valid_voices else "Aoede"

        output_path_str = inputs.get("output_path")
        output_path = Path(output_path_str).resolve() if output_path_str else Path("output.mp3").resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        keys = self._get_api_keys()
        if not keys:
            return self._fallback_edge_tts(inputs, output_path, reason="No Gemini API keys found.")

        try:
            from google import genai
            from google.genai import types
        except ImportError:
            return self._fallback_edge_tts(inputs, output_path, reason="google-genai package missing.")

        model_candidates = ["gemini-3.8-flash-tts", "gemini-2.5-flash-preview-tts"]
        audio_bytes = None
        mime_type = "audio/wav"
        last_err = None

        for key in keys:
            client = genai.Client(api_key=key)
            for model_name in model_candidates:
                try:
                    config = types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=voice
                                )
                            )
                        ),
                    )
                    resp = client.models.generate_content(
                        model=model_name,
                        contents=text,
                        config=config,
                    )
                    if resp.candidates and resp.candidates[0].content and resp.candidates[0].content.parts:
                        part = resp.candidates[0].content.parts[0]
                        if hasattr(part, "inline_data") and part.inline_data and part.inline_data.data:
                            audio_bytes = part.inline_data.data
                            mime_type = part.inline_data.mime_type or "audio/wav"
                            break
                except Exception as e:
                    last_err = e
                    continue
            if audio_bytes is not None:
                break

        if audio_bytes is None:
            return self._fallback_edge_tts(inputs, output_path, reason=str(last_err))

        start_time = time.time()
        temp_wav = None
        try:
            if output_path.suffix.lower() == ".mp3":
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                    temp_wav = Path(tf.name)

                if "pcm" in mime_type.lower() or mime_type.startswith("audio/L16"):
                    with wave.open(str(temp_wav), "wb") as wav_file:
                        wav_file.setnchannels(1)
                        wav_file.setsampwidth(2)
                        wav_file.setframerate(24000)
                        wav_file.writeframes(audio_bytes)
                else:
                    temp_wav.write_bytes(audio_bytes)

                cmd = [
                    "ffmpeg", "-y",
                    "-i", str(temp_wav),
                    "-codec:a", "libmp3lame",
                    "-qscale:a", "2",
                    str(output_path),
                ]
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                if "pcm" in mime_type.lower() or mime_type.startswith("audio/L16"):
                    with wave.open(str(output_path), "wb") as wav_file:
                        wav_file.setnchannels(1)
                        wav_file.setsampwidth(2)
                        wav_file.setframerate(24000)
                        wav_file.writeframes(audio_bytes)
                else:
                    output_path.write_bytes(audio_bytes)
        except Exception as ex:
            return self._fallback_edge_tts(inputs, output_path, reason=f"Audio packaging failed: {ex}")
        finally:
            if temp_wav and temp_wav.is_file():
                try:
                    temp_wav.unlink()
                except OSError:
                    pass

        if not output_path.is_file() or output_path.stat().st_size == 0:
            return self._fallback_edge_tts(inputs, output_path, reason="Gemini output file missing or empty.")

        duration = round(time.time() - start_time, 2)
        return ToolResult(
            success=True,
            data={
                "provider": "gemini",
                "voice": voice,
                "output": str(output_path),
                "file_size_bytes": output_path.stat().st_size,
                "duration_seconds": duration,
                "text_length": len(text),
            },
            artifacts=[str(output_path)],
        )

    def _fallback_edge_tts(self, inputs: dict[str, Any], output_path: Path, reason: str = "") -> ToolResult:
        try:
            from tools.tool_registry import registry
            edge_tool = registry.get("edge_tts")
            if edge_tool:
                edge_inputs = dict(inputs)
                edge_inputs["voice"] = "en-US-AndrewMultilingualNeural"
                edge_inputs["output_path"] = str(output_path)
                return edge_tool.execute(edge_inputs)
        except Exception:
            pass
        return ToolResult(
            success=False,
            error=f"Gemini TTS synthesis failed: {reason or 'No keys or models succeeded'}",
        )
