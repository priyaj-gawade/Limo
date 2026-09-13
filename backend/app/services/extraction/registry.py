"""Extractor registry mapping MIME types and extensions to appropriate extractors."""

import logging
from typing import List, Optional

from ...exceptions import StorageError
from .base import BaseExtractor
from .document import DocxExtractor, HtmlExtractor, TextMarkdownExtractor
from .media import MediaExtractor
from .pdf import PdfExtractor
from .tabular import SpreadsheetExtractor

logger = logging.getLogger("limo.services.extraction.registry")


class ExtractorRegistry:
    """Registry maintaining extractor implementations and dispatching based on file types."""

    def __init__(self):
        self._extractors: List[BaseExtractor] = [
            DocxExtractor(),
            PdfExtractor(),
            SpreadsheetExtractor(),
            HtmlExtractor(),
            MediaExtractor(),
            TextMarkdownExtractor(),  # Text fallback
        ]

    def register_extractor(self, extractor: BaseExtractor) -> None:
        """Register a custom extractor with high priority."""
        self._extractors.insert(0, extractor)

    def get_extractor(self, mime_type: str, filename: str) -> BaseExtractor:
        """Find the first matching extractor for the given MIME type and filename."""
        for extractor in self._extractors:
            if extractor.can_handle(mime_type, filename):
                return extractor

        raise StorageError(f"No extractor registered to handle file '{filename}' with MIME type '{mime_type}'")


extractor_registry = ExtractorRegistry()
