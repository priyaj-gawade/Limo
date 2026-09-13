"""Base extractor abstract interface."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional

from .models import ExtractedDocument


class BaseExtractor(ABC):
    """Abstract interface for all document and media extractors."""

    @abstractmethod
    def can_handle(self, mime_type: str, filename: str) -> bool:
        """Return True if this extractor can parse the given MIME type or filename."""
        pass

    @abstractmethod
    async def extract(
        self,
        source_id: str,
        filename: str,
        content: Optional[bytes] = None,
        metadata: Optional[Dict[str, Any]] = None,
        file_path: Optional[Path] = None,
    ) -> ExtractedDocument:
        """Extract structured headings, paragraphs, tables, and raw text from file path or binary content."""
        pass
