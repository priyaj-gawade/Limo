"""Provider adapters isolating SDK and protocol specifics."""

from .base import BaseProviderAdapter
from .gemini import GeminiAdapter

__all__ = [
    "BaseProviderAdapter",
    "GeminiAdapter",
]
