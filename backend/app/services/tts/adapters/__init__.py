"""TTS Provider Adapters Package."""

from .azure import AzureTTSAdapter
from .openai import OpenAITTSAdapter
from .piper import PiperTTSAdapter
from .edge import EdgeTTSAdapter
from .gemini import GeminiTTSAdapter

__all__ = [
    "GeminiTTSAdapter",
    "EdgeTTSAdapter",
    "PiperTTSAdapter",
    "AzureTTSAdapter",
    "OpenAITTSAdapter",
]
