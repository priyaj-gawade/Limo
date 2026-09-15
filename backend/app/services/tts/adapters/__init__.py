"""TTS Provider Adapters Package."""

from .azure import AzureTTSAdapter
from .openai import OpenAITTSAdapter
from .piper import PiperTTSAdapter
from .edge import EdgeTTSAdapter

__all__ = [
    "AzureTTSAdapter",
    "OpenAITTSAdapter",
    "PiperTTSAdapter",
    "EdgeTTSAdapter",
]
