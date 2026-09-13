"""Boundary adapters for external subsystems."""

from .genoffice_adapter import GenOfficeBoundaryContract
from .video_adapter import VideoEngineBoundaryContract

__all__ = [
    "GenOfficeBoundaryContract",
    "VideoEngineBoundaryContract",
]
