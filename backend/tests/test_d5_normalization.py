"""Unit and integration tests for Phase D5.3: Normalization & Content Processing."""

import pytest
from app.models.enums import SourceType
from app.services.extraction.models import (
    ExtractedDocument,
    ExtractedHeading,
    ExtractedMediaItem,
    ExtractedParagraph,
    ExtractedTable,
)
from app.services.normalization.models import (
    NormalizedDocument,
    NormalizedSection,
    NormalizedTable,
)
from app.services.normalization.service import NormalizationService, normalization_service


class TestNormalizationTextCleaning:
    """Test suite for Unicode, smart quote, whitespace, and dash standardization."""

    def test_clean_text_unicode_and_smart_quotes(self):
        dirty = "“Smart quotes” and ‘apostrophe’ with \u00a0non-breaking\u00a0space and en\u2013dash and em\u2014dash."
        cleaned = NormalizationService.clean_text(dirty)
        assert '"Smart quotes"' in cleaned
        assert "'apostrophe'" in cleaned
        assert "non-breaking space" in cleaned
        assert "en-dash" in cleaned
        assert "em--dash" in cleaned

    def test_clean_text_collapses_whitespace_and_newlines(self):
        messy = "Line one with   extra    spaces.   \r\n\r\n\r\n\r\nLine two after empty lines."
        cleaned = NormalizationService.clean_text(messy)
        assert "Line one with extra spaces." in cleaned
        assert "\n\n" in cleaned
        assert "\n\n\n" not in cleaned

    def test_clean_text_empty_input(self):
        assert NormalizationService.clean_text("") == ""
        assert NormalizationService.clean_text("   \n\n  ") == ""


class TestNormalizationDocumentMapping:
    """Test suite verifying ExtractedDocument mapping into NormalizedDocument."""

    def test_heading_and_paragraph_hierarchy_mapping(self):
        doc = ExtractedDocument(
            source_id="src_doc_01",
            source_name="annual_report.docx",
            source_type=SourceType.FILE,
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headings=[
                ExtractedHeading(text="1. Executive Summary", level=1),
                ExtractedHeading(text="1.1 Financial Highlights", level=2),
            ],
            paragraphs=[
                ExtractedParagraph(text="Opening intro before section 1.", section_title=None, page_number=1),
                ExtractedParagraph(text="Q4 revenue reached record levels.", section_title="1. Executive Summary", page_number=1),
                ExtractedParagraph(text="Gross margins expanded by 340 bps.", section_title="1.1 Financial Highlights", page_number=2),
            ],
            tables=[],
            raw_text="Full raw content text.",
        )

        norm = normalization_service.normalize_extracted_document(doc)
        assert isinstance(norm, NormalizedDocument)
        assert norm.source_id == "src_doc_01"
        assert len(norm.sections) == 3

        # Orphan section
        assert norm.sections[0].title is None
        assert "Opening intro" in norm.sections[0].content
        assert norm.sections[0].page_number == 1

        # Section 1
        assert norm.sections[1].title == "1. Executive Summary"
        assert norm.sections[1].level == 1
        assert "Q4 revenue" in norm.sections[1].content
        assert norm.sections[1].page_number == 1

        # Section 2
        assert norm.sections[2].title == "1.1 Financial Highlights"
        assert norm.sections[2].level == 2
        assert "Gross margins" in norm.sections[2].content
        assert norm.sections[2].page_number == 2

    def test_table_normalization_and_anchor_preservation(self):
        doc = ExtractedDocument(
            source_id="src_tbl_01",
            source_name="balance_sheet.xlsx",
            source_type=SourceType.FILE,
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headings=[],
            paragraphs=[],
            tables=[
                ExtractedTable(
                    name="Q4 Balance",
                    headers=["Asset Category  ", "  2025 Value", "2026 Value "],
                    rows=[
                        ["Cash & Equivalents", "$12.4M", "$15.8M"],
                        ["", "   ", ""],  # Empty row to be filtered
                        ["Short-term Debt", "$3.1M", "$2.8M"],
                    ],
                )
            ],
            raw_text="",
        )

        norm = normalization_service.normalize_extracted_document(doc)
        assert len(norm.tables) == 1
        tbl = norm.tables[0]
        assert tbl.name == "Q4 Balance"
        assert tbl.headers == ["Asset Category", "2025 Value", "2026 Value"]
        # Empty row must have been dropped
        assert len(tbl.rows) == 2
        assert tbl.rows[0] == ["Cash & Equivalents", "$12.4M", "$15.8M"]
        assert tbl.rows[1] == ["Short-term Debt", "$3.1M", "$2.8M"]

    def test_media_transcript_timestamp_segmentation(self):
        doc = ExtractedDocument(
            source_id="src_media_01",
            source_name="keynote.mp4",
            source_type=SourceType.VIDEO,
            mime_type="video/mp4",
            headings=[],
            paragraphs=[],
            tables=[],
            media_items=[
                ExtractedMediaItem(
                    filename="keynote.mp4",
                    media_type="video",
                    transcript=(
                        "[00:00] Welcome to the annual symposium.\n"
                        "[01:15] Today we unveil our new quantum architecture.\n"
                        "[03:40] Closing Q&A session."
                    ),
                )
            ],
            raw_text="",
        )

        norm = normalization_service.normalize_extracted_document(doc)
        assert len(norm.sections) == 3
        assert norm.sections[0].timestamp == "00:00"
        assert "Welcome to the annual symposium" in norm.sections[0].content
        assert norm.sections[1].timestamp == "01:15"
        assert "quantum architecture" in norm.sections[1].content
        assert norm.sections[2].timestamp == "03:40"
        assert "Closing Q&A" in norm.sections[2].content
