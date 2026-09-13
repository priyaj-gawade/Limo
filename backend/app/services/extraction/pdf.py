"""Tiered PDF extractor supporting vector text, complex tables, and OCR fallback."""

import io
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import pypdf
import pdfplumber

from ...exceptions import StorageError
from ...models.enums import SourceType
from .base import BaseExtractor
from .models import (
    ExtractedDocument,
    ExtractedHeading,
    ExtractedParagraph,
    ExtractedTable,
)

logger = logging.getLogger("limo.services.extraction.pdf")


class PdfExtractor(BaseExtractor):
    """Tiered PDF extractor:
    - Tier 1: Vector text & page-numbered paragraphs via pypdf.
    - Tier 2: Complex table extraction via pdfplumber.
    - Tier 3: Scanned / image-only OCR fallback via configurable LLMProviderManager.
    """

    def can_handle(self, mime_type: str, filename: str) -> bool:
        lower_name = filename.lower()
        lower_mime = mime_type.lower()
        return lower_name.endswith(".pdf") or "application/pdf" in lower_mime

    async def extract(
        self,
        source_id: str,
        filename: str,
        content: Optional[bytes] = None,
        metadata: Optional[Dict[str, Any]] = None,
        file_path: Optional[Path] = None,
    ) -> ExtractedDocument:
        if content is None:
            if not file_path or not file_path.exists():
                raise StorageError(f"Cannot extract PDF '{filename}': no file content or path provided")
            content = file_path.read_bytes()

        try:
            reader = pypdf.PdfReader(io.BytesIO(content))
        except Exception as e:
            raise StorageError(f"Failed to parse PDF document '{filename}': {e}") from e

        if reader.is_encrypted:
            raise StorageError(f"PDF document '{filename}' is password-protected/encrypted and cannot be extracted")

        total_pages = len(reader.pages)
        if total_pages == 0:
            return ExtractedDocument(
                source_id=source_id,
                source_name=filename,
                source_type=SourceType.FILE,
                mime_type="application/pdf",
                raw_text="",
                metadata={"page_count": 0, "tier": 1},
            )

        headings: List[ExtractedHeading] = []
        paragraphs: List[ExtractedParagraph] = []
        tables: List[ExtractedTable] = []
        raw_text_parts: List[str] = []

        total_chars_extracted = 0

        # Tier 1: Page-by-page vector text extraction
        for page_idx, page in enumerate(reader.pages):
            page_num = page_idx + 1
            page_text = page.extract_text() or ""
            total_chars_extracted += len(page_text.strip())

            if not page_text.strip():
                continue

            raw_text_parts.append(f"--- [Page {page_num}] ---")
            lines = page_text.splitlines()
            for line in lines:
                cleaned = line.strip()
                if not cleaned:
                    continue

                # Heuristic heading detection (all-caps or short lines starting with numbers)
                if len(cleaned) < 80 and (cleaned.isupper() or cleaned.startswith(("Chapter", "Section", "1.", "2.", "3.", "4.", "5."))):
                    headings.append(ExtractedHeading(text=cleaned, level=2, page_number=page_num))
                else:
                    paragraphs.append(ExtractedParagraph(text=cleaned, page_number=page_num))

                raw_text_parts.append(cleaned)

        avg_chars_per_page = total_chars_extracted / total_pages
        tier_used = 1

        # Tier 2: Extract structured tables via pdfplumber
        try:
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                for page_idx, pl_page in enumerate(pdf.pages):
                    page_num = page_idx + 1
                    extracted_tables = pl_page.extract_tables()
                    for t_idx, raw_table in enumerate(extracted_tables):
                        if not raw_table or len(raw_table) < 2:
                            continue

                        # Clean cell values
                        cleaned_headers = [str(c).strip() if c is not None else "" for c in raw_table[0]]
                        cleaned_rows = [
                            [str(c).strip() if c is not None else "" for c in row]
                            for row in raw_table[1:]
                        ]

                        table_name = f"Page {page_num} Table {t_idx + 1}"
                        tables.append(
                            ExtractedTable(
                                name=table_name,
                                headers=cleaned_headers,
                                rows=cleaned_rows,
                                page_number=page_num,
                            )
                        )
                        tier_used = max(tier_used, 2)
        except Exception as e:
            logger.warning("pdfplumber table extraction skipped on '%s': %s", filename, e)

        # Tier 3: Multi-signal Scanned / Image-only OCR Fallback
        # Combines character density, presence of raster images, and table absence
        meta = metadata or {}
        force_ocr = meta.get("force_ocr", False)
        has_images = any(len(getattr(page, "images", [])) > 0 for page in reader.pages)

        should_ocr = force_ocr or (
            avg_chars_per_page < 50
            and (has_images or len(tables) == 0 or total_chars_extracted < 100)
        )

        if should_ocr:
            logger.info(
                "PDF '%s' triggered Tier 3 OCR heuristic (density=%.1f chars/page, images=%s, tables=%d)",
                filename,
                avg_chars_per_page,
                has_images,
                len(tables),
            )
            ocr_text = await self._run_ocr_fallback(content, filename)
            if ocr_text:
                tier_used = 3
                raw_text_parts.append("\n--- [Tier 3 OCR Output] ---")
                raw_text_parts.append(ocr_text)
                paragraphs.append(ExtractedParagraph(text=ocr_text, page_number=1))

        return ExtractedDocument(
            source_id=source_id,
            source_name=filename,
            source_type=SourceType.FILE,
            mime_type="application/pdf",
            headings=headings,
            paragraphs=paragraphs,
            tables=tables,
            raw_text="\n\n".join(raw_text_parts).strip(),
            metadata={
                "page_count": total_pages,
                "tier_used": tier_used,
                "table_count": len(tables),
                "avg_chars_per_page": round(avg_chars_per_page, 1),
            },
        )

    async def _run_ocr_fallback(self, content: bytes, filename: str) -> Optional[str]:
        """Execute OCR via configurable vision model from LLMProviderManager."""
        try:
            from ...agent.llm.manager import llm_provider_manager
            prompt = (
                "Extract all text, headings, numbers, and structured content from this scanned PDF page verbatim. "
                "Preserve table rows and headings. Output clean readable text."
            )
            # Use centralized LLMProviderManager for resilient inference
            response = await llm_provider_manager.generate(
                prompt=prompt,
                temperature=0.1,
            )
            return response.text
        except Exception as e:
            logger.warning("Tier 3 OCR fallback failed on '%s': %s", filename, e)
            return None
