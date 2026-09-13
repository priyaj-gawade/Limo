"""Normalization Service (Phase D5.3).

Standardizes disparate extractor outputs into NormalizedDocument models.
Does NOT re-read raw source files from disk; strictly consumes ExtractedDocument.
"""

import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional

from ..extraction.models import ExtractedDocument, ExtractedParagraph, ExtractedTable
from .models import NormalizedDocument, NormalizedSection, NormalizedTable

logger = logging.getLogger("limo.services.normalization")


class NormalizationService:
    """Deterministic normalization service for extracted documents and media."""

    @staticmethod
    def clean_text(text: str) -> str:
        """Standardize Unicode, normalize whitespace, ligatures, and quotation marks."""
        if not text:
            return ""

        # 1. Unicode NFKC Normalization (standardizes ligatures, accents, fullwidth characters)
        normalized = unicodedata.normalize("NFKC", text)

        # 2. Normalize smart quotation marks, apostrophes, and dashes
        replacements = {
            "\u2018": "'",  # Left single quotation mark
            "\u2019": "'",  # Right single quotation mark / curly apostrophe
            "\u201a": "'",  # Single low-9 quotation mark
            "\u201b": "'",  # Single high-reversed-9 quotation mark
            "\u201c": '"',  # Left double quotation mark
            "\u201d": '"',  # Right double quotation mark
            "\u201e": '"',  # Double low-9 quotation mark
            "\u2013": "-",  # En dash
            "\u2014": "--", # Em dash
            "\u00a0": " ",  # Non-breaking space
            "\u200b": "",   # Zero-width space
            "\ufeff": "",   # Byte order mark
            "\r\n": "\n",   # CRLF -> LF
            "\r": "\n",     # CR -> LF
        }
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)

        # 3. Collapse multiple horizontal spaces and tabs while preserving newlines
        lines = []
        for line in normalized.split("\n"):
            cleaned_line = re.sub(r"[ \t]+", " ", line).strip()
            lines.append(cleaned_line)

        # 4. Collapse multiple blank lines (max 2 consecutive newlines)
        result = "\n".join(lines)
        result = re.sub(r"\n{3,}", "\n\n", result)
        return result.strip()

    def normalize_extracted_document(self, doc: ExtractedDocument) -> NormalizedDocument:
        """Convert ExtractedDocument into standardized NormalizedDocument.
        
        Preserves all section titles, hierarchy levels, page numbers, timestamps, and table structures.
        """
        sections: List[NormalizedSection] = []
        tables: List[NormalizedTable] = []

        # 1. Normalize Tables
        for tbl in doc.tables:
            cleaned_headers = [self.clean_text(h) for h in tbl.headers]
            cleaned_rows: List[List[str]] = []
            for row in tbl.rows:
                # Filter out completely empty rows
                cleaned_row = [self.clean_text(cell) for cell in row]
                if any(cleaned_row):
                    cleaned_rows.append(cleaned_row)

            tables.append(
                NormalizedTable(
                    name=tbl.name,
                    headers=cleaned_headers,
                    rows=cleaned_rows,
                    source_reference=tbl.name,
                )
            )

        # 2. Map Headings & Paragraphs into NormalizedSections
        if doc.headings:
            # Group paragraphs by their preceding heading
            heading_map: Dict[Optional[str], List[ExtractedParagraph]] = {}
            current_heading_title: Optional[str] = None

            for para in doc.paragraphs:
                # Paragraph may have section_title already attached from extractor
                sec_title = para.section_title or current_heading_title
                heading_map.setdefault(sec_title, []).append(para)

            # Build NormalizedSection for each heading
            heading_levels = {h.text: h.level for h in doc.headings}
            matched_titles = set()

            for heading in doc.headings:
                h_text = heading.text
                matched_titles.add(h_text)
                paras = heading_map.get(h_text, [])
                content_text = self.clean_text("\n\n".join(p.text for p in paras))
                page_no = paras[0].page_number if paras and paras[0].page_number is not None else None

                sections.append(
                    NormalizedSection(
                        title=h_text,
                        level=heading.level,
                        content=content_text or h_text,
                        page_number=page_no,
                    )
                )

            # Check for orphan paragraphs before the first heading
            orphan_paras = heading_map.get(None, [])
            if orphan_paras:
                orphan_content = self.clean_text("\n\n".join(p.text for p in orphan_paras))
                if orphan_content:
                    sections.insert(
                        0,
                        NormalizedSection(
                            title=None,
                            level=1,
                            content=orphan_content,
                            page_number=orphan_paras[0].page_number if orphan_paras[0].page_number is not None else None,
                        ),
                    )
        elif doc.paragraphs:
            # Document has paragraphs but no explicit headings (e.g. TXT, simple article)
            # Group paragraphs by page if available, else group into standard sections
            paras_by_page: Dict[Optional[int], List[str]] = {}
            for p in doc.paragraphs:
                p_text = self.clean_text(p.text)
                if p_text:
                    paras_by_page.setdefault(p.page_number, []).append(p_text)

            for page_num, p_texts in sorted(paras_by_page.items(), key=lambda item: (item[0] is None, item[0])):
                title = f"Page {page_num}" if page_num is not None else doc.source_name
                sections.append(
                    NormalizedSection(
                        title=title,
                        level=1,
                        content="\n\n".join(p_texts),
                        page_number=page_num,
                    )
                )
        elif doc.raw_text.strip():
            # Fallback for plain unsegmented text
            sections.append(
                NormalizedSection(
                    title=doc.source_name,
                    level=1,
                    content=self.clean_text(doc.raw_text),
                )
            )

        # 3. Map Media Items (transcripts and timeline events) into NormalizedSections
        for media in doc.media_items:
            if media.transcript:
                clean_transcript = self.clean_text(media.transcript)
                # Parse timestamped blocks (e.g. [01:23] Speaker: text)
                timestamp_blocks = re.findall(r"\[(\d{1,2}:\d{2}(?::\d{2})?)\]\s*([^\n\[]+)", clean_transcript)
                if timestamp_blocks:
                    for ts, content in timestamp_blocks:
                        sections.append(
                            NormalizedSection(
                                title=f"Media Segment [{ts}]",
                                level=2,
                                content=content.strip(),
                                timestamp=ts,
                            )
                        )
                else:
                    sections.append(
                        NormalizedSection(
                            title=f"Media Transcript ({media.filename})",
                            level=1,
                            content=clean_transcript,
                        )
                    )

        # 4. Generate Clean Consolidated raw_text
        section_texts = [
            f"## {s.title}\n{s.content}" if s.title else s.content
            for s in sections
            if s.content
        ]
        table_texts = []
        for t in tables:
            t_str = f"Table: {t.name}\n" + " | ".join(t.headers) + "\n"
            for row in t.rows[:50]:  # Cap sample table in raw text
                t_str += " | ".join(row) + "\n"
            table_texts.append(t_str)

        all_text_parts = section_texts + table_texts
        consolidated_raw_text = self.clean_text("\n\n".join(all_text_parts))

        return NormalizedDocument(
            source_id=doc.source_id,
            source_name=doc.source_name,
            source_type=doc.source_type,
            mime_type=doc.mime_type,
            sections=sections,
            tables=tables,
            raw_text=consolidated_raw_text or self.clean_text(doc.raw_text),
            metadata={
                **doc.metadata,
                "normalized": True,
                "section_count": len(sections),
                "table_count": len(tables),
            },
        )

    # Alias for convenience
    normalize = normalize_extracted_document



normalization_service = NormalizationService()
