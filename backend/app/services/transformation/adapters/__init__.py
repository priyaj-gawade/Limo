"""Native deliverable adapters package (Phase D6.3)."""

from .base import BaseNativeAdapter, GeneratedContent
from .infographic_adapter import NativeInfographicAdapter
from .markdown_adapter import NativeHtmlAdapter, NativeMarkdownAdapter
from .social_adapter import NativeSocialAdapter
from .video_adapter import OpenMontageVideoAdapter

__all__ = [
    "BaseNativeAdapter",
    "GeneratedContent",
    "NativeMarkdownAdapter",
    "NativeHtmlAdapter",
    "NativeSocialAdapter",
    "NativeInfographicAdapter",
    "OpenMontageVideoAdapter",
]
