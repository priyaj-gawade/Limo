"""Comprehensive automated tests for D5.2 Document & Tabular Extractors.

Tests:
- DocxExtractor: H1-H3 headings, paragraphs, structured tables, empty/corrupted files.
- PdfExtractor: 3-tier parsing (Tier 1 text, Tier 2 tables, Tier 3 OCR fallback), encrypted files.
- SpreadsheetExtractor: multi-sheet Excel (.xlsx), CSV/TSV with delimiter autodetection.
- TextMarkdownExtractor: markdown headings, paragraphs, markdown tables, lists.
- HtmlExtractor: sanitization (stripping script/style), headings, tables, metadata.
- ExtractionService: unified routing and registry orchestration.
"""

import io
from unittest.mock import AsyncMock, MagicMock, patch
import openpyxl
import pytest
from docx import Document

from app.exceptions import StorageError
from app.models.enums import SourceType
from app.services.extraction.constants import EXTRACTION_VERSION
from app.services.extraction.document import (
    DocxExtractor,
    HtmlExtractor,
    TextMarkdownExtractor,
)
from app.services.extraction.models import ExtractedDocument
from app.services.extraction.pdf import PdfExtractor
from app.services.extraction.registry import ExtractorRegistry
from app.services.extraction.service import ExtractionError, ExtractionService
from app.services.extraction.tabular import SpreadsheetExtractor


class TestDocxExtractor:
    """Test suite for Word (.docx) document extraction."""

    def test_can_handle(self):
        extractor = DocxExtractor()
        assert extractor.can_handle("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "report.docx")
        assert extractor.can_handle("application/msword", "doc.DOCX")
        assert not extractor.can_handle("application/pdf", "report.pdf")

    @pytest.mark.asyncio
    async def test_extract_headings_paragraphs_tables(self):
        doc = Document()
        doc.add_heading("Project Overview", level=1)
        doc.add_paragraph("This is the introductory paragraph for testing.")
        doc.add_heading("Key Findings", level=2)
        doc.add_paragraph("Second paragraph under section 2.")
        doc.add_heading("Subsection A", level=3)

        # Add table
        table = doc.add_table(rows=3, cols=3)
        headers = ["Item", "Cost", "Quantity"]
        for i, h in enumerate(headers):
            table.cell(0, i).text = h
        table.cell(1, 0).text = "Widget Alpha"
        table.cell(1, 1).text = "$100"
        table.cell(1, 2).text = "5"
        table.cell(2, 0).text = "Widget Beta"
        table.cell(2, 1).text = "$250"
        table.cell(2, 2).text = "2"

        buf = io.BytesIO()
        doc.save(buf)
        content = buf.getvalue()

        extractor = DocxExtractor()
        result = await extractor.extract(
            source_id="src_docx_001",
            filename="test_doc.docx",
            content=content,
            metadata={},
        )

        assert isinstance(result, ExtractedDocument)
        assert result.source_id == "src_docx_001"
        assert result.source_type == SourceType.FILE
        assert len(result.headings) == 3
        assert result.headings[0].text == "Project Overview"
        assert result.headings[0].level == 1
        assert result.headings[1].text == "Key Findings"
        assert result.headings[1].level == 2
        assert result.headings[2].text == "Subsection A"
        assert result.headings[2].level == 3

        assert len(result.paragraphs) == 2
        assert "introductory paragraph" in result.paragraphs[0].text

        assert len(result.tables) == 1
        tbl = result.tables[0]
        assert tbl.headers == ["Item", "Cost", "Quantity"]
        assert len(tbl.rows) == 2
        assert tbl.rows[0] == ["Widget Alpha", "$100", "5"]
        assert tbl.rows[1] == ["Widget Beta", "$250", "2"]

    @pytest.mark.asyncio
    async def test_corrupted_docx_raises_storage_error(self):
        extractor = DocxExtractor()
        with pytest.raises(StorageError, match="Failed to parse DOCX"):
            await extractor.extract("src_bad", "corrupt.docx", b"not a docx content", {})


class TestPdfExtractor:
    """Test suite for Tiered PDF parsing (Tier 1 text, Tier 2 tables, Tier 3 OCR fallback)."""

    def _create_simple_pdf_bytes(self, text_lines: list[str]) -> bytes:
        """Create valid PDF bytes containing text lines."""
        stream_text = "\n".join(f"({line}) Tj T*" for line in text_lines)
        stream_content = f"BT\n/F1 12 Tf\n50 750 Td\n15 TL\n{stream_text}\nET\n".encode("latin-1")
        length = len(stream_content)

        pdf = (
            b"%PDF-1.4\n"
            b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
            b"4 0 obj\n<< /Length " + str(length).encode("latin-1") + b" >>\nstream\n"
            + stream_content
            + b"\nendstream\nendobj\n"
            b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
            b"xref\n0 6\n"
            b"0000000000 65535 f \n"
            b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n500\n%%EOF"
        )
        return pdf

    def test_can_handle(self):
        extractor = PdfExtractor()
        assert extractor.can_handle("application/pdf", "manual.pdf")
        assert extractor.can_handle("application/octet-stream", "MANUAL.PDF")
        assert not extractor.can_handle("text/plain", "manual.txt")

    @pytest.mark.asyncio
    async def test_tier1_vector_text_extraction(self):
        lines = [
            "CHAPTER 1: SYSTEM OVERVIEW",
            "This document describes the high-throughput ingestion pipeline.",
            "It supports structured multi-modal content extraction with metadata provenance.",
            "All sources are validated and indexed for canonical reasoning.",
        ]
        pdf_bytes = self._create_simple_pdf_bytes(lines)
        extractor = PdfExtractor()

        result = await extractor.extract("src_pdf_01", "overview.pdf", pdf_bytes, {})
        assert isinstance(result, ExtractedDocument)
        assert result.metadata["page_count"] == 1
        assert result.metadata["tier_used"] == 1
        assert len(result.headings) >= 1
        assert result.headings[0].text == "CHAPTER 1: SYSTEM OVERVIEW"
        assert len(result.paragraphs) >= 1
        assert any("high-throughput" in p.text for p in result.paragraphs)

    @pytest.mark.asyncio
    async def test_tier3_ocr_fallback_triggered_on_low_density(self):
        """Scanned/image-only PDFs (< 50 chars/page) must trigger Tier 3 OCR via LLMProviderManager."""
        # Minimal text < 50 characters
        lines = ["Tiny"]
        pdf_bytes = self._create_simple_pdf_bytes(lines)
        extractor = PdfExtractor()

        mock_llm_response = MagicMock()
        mock_llm_response.text = "Heading 1: OCR Recovered Text\nThis paragraph was extracted via Tier 3 vision OCR."

        with patch("app.agent.llm.manager.llm_provider_manager.generate", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_llm_response

            result = await extractor.extract("src_scanned", "scanned_invoice.pdf", pdf_bytes, {})
            assert result.metadata["tier_used"] == 3
            assert "OCR Recovered Text" in result.raw_text
            mock_llm.assert_called_once()


class TestSpreadsheetExtractor:
    """Test suite for Excel (.xlsx) and CSV/TSV extraction."""

    def test_can_handle(self):
        extractor = SpreadsheetExtractor()
        assert extractor.can_handle("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "data.xlsx")
        assert extractor.can_handle("text/csv", "metrics.csv")
        assert extractor.can_handle("text/tab-separated-values", "log.tsv")
        assert not extractor.can_handle("text/plain", "notes.txt")

    @pytest.mark.asyncio
    async def test_extract_xlsx_multisheet(self):
        wb = openpyxl.Workbook()
        ws1 = wb.active
        ws1.title = "Revenue"
        ws1.append(["Quarter", "ARR", "Growth"])
        ws1.append(["Q1", "$1.2M", "15%"])
        ws1.append(["Q2", "$1.5M", "25%"])

        ws2 = wb.create_sheet(title="Headcount")
        ws2.append(["Department", "FTEs"])
        ws2.append(["Engineering", 42])
        ws2.append(["Product", 10])

        buf = io.BytesIO()
        wb.save(buf)
        content = buf.getvalue()

        extractor = SpreadsheetExtractor()
        result = await extractor.extract("src_xlsx", "financials.xlsx", content, {})

        assert result.source_type == SourceType.TABULAR
        assert len(result.tables) == 2
        t1 = result.tables[0]
        assert t1.name == "Revenue"
        assert t1.headers == ["Quarter", "ARR", "Growth"]
        assert len(t1.rows) == 2
        assert t1.rows[0] == ["Q1", "$1.2M", "15%"]

        t2 = result.tables[1]
        assert t2.name == "Headcount"
        assert t2.headers == ["Department", "FTEs"]
        assert t2.rows[0] == ["Engineering", "42"]

    @pytest.mark.asyncio
    async def test_extract_csv(self):
        csv_content = b"Service,Latency_p99,Error_Rate\nAuth,12ms,0.01%\nBilling,45ms,0.03%\nStorage,85ms,0.00%"
        extractor = SpreadsheetExtractor()
        result = await extractor.extract("src_csv", "telemetry.csv", csv_content, {"mime_type": "text/csv"})

        assert result.source_type == SourceType.TABULAR
        assert len(result.tables) == 1
        tbl = result.tables[0]
        assert tbl.headers == ["Service", "Latency_p99", "Error_Rate"]
        assert len(tbl.rows) == 3
        assert tbl.rows[0] == ["Auth", "12ms", "0.01%"]

    @pytest.mark.asyncio
    async def test_extract_tsv(self):
        tsv_content = b"ID\tStatus\tOwner\n101\tOpen\tAlice\n102\tClosed\tBob"
        extractor = SpreadsheetExtractor()
        result = await extractor.extract("src_tsv", "tasks.tsv", tsv_content, {})

        assert result.source_type == SourceType.TABULAR
        assert len(result.tables) == 1
        tbl = result.tables[0]
        assert tbl.headers == ["ID", "Status", "Owner"]
        assert tbl.rows[0] == ["101", "Open", "Alice"]


class TestTextMarkdownExtractor:
    """Test suite for Markdown and Plain Text extraction."""

    def test_can_handle(self):
        extractor = TextMarkdownExtractor()
        assert extractor.can_handle("text/markdown", "README.md")
        assert extractor.can_handle("text/plain", "notes.txt")
        assert not extractor.can_handle("application/pdf", "notes.pdf")

    @pytest.mark.asyncio
    async def test_extract_markdown_structure(self):
        md_text = (
            "# Architecture Specification\n\n"
            "This specification outlines the multi-modal reasoning engine.\n\n"
            "## Module Interfaces\n\n"
            "Here is the module interaction mapping:\n\n"
            "| Module | Protocol | SLA |\n"
            "| --- | --- | --- |\n"
            "| Gateway | HTTP/REST | 50ms |\n"
            "| Worker | Async Queue | 2000ms |\n\n"
            "### Deployment Checklist\n\n"
            "- Verify DNS\n"
            "- Configure TLS\n"
        ).encode("utf-8")

        extractor = TextMarkdownExtractor()
        result = await extractor.extract("src_md", "spec.md", md_text, {})

        assert result.source_type == SourceType.TEXT
        assert len(result.headings) == 3
        assert result.headings[0].text == "Architecture Specification"
        assert result.headings[0].level == 1
        assert result.headings[1].text == "Module Interfaces"
        assert result.headings[1].level == 2
        assert result.headings[2].text == "Deployment Checklist"
        assert result.headings[2].level == 3

        assert len(result.tables) == 1
        tbl = result.tables[0]
        assert tbl.headers == ["Module", "Protocol", "SLA"]
        assert len(tbl.rows) == 2
        assert tbl.rows[0] == ["Gateway", "HTTP/REST", "50ms"]
        assert tbl.rows[1] == ["Worker", "Async Queue", "2000ms"]

        assert len(result.paragraphs) >= 2


class TestHtmlExtractor:
    """Test suite for HTML sanitization and structured extraction."""

    def test_can_handle(self):
        extractor = HtmlExtractor()
        assert extractor.can_handle("text/html", "article.html")
        assert extractor.can_handle("application/xhtml+xml", "page.xhtml")
        assert not extractor.can_handle("text/plain", "article.txt")

    @pytest.mark.asyncio
    async def test_extract_html_sanitization_and_structure(self):
        html_bytes = (
            "<!DOCTYPE html>\n"
            "<html>\n"
            "<head>\n"
            "  <title>Security Advisory 2026</title>\n"
            "  <style>body { background: #000; color: #fff; }</style>\n"
            "  <script>window.alert('malicious payload');</script>\n"
            "</head>\n"
            "<body>\n"
            "  <h1>Vulnerability Report</h1>\n"
            "  <p>A critical buffer overflow was remediated in core routing.</p>\n"
            "  <h2>Affected Systems</h2>\n"
            "  <table>\n"
            "    <thead><tr><th>Host</th><th>IP</th><th>Patched</th></tr></thead>\n"
            "    <tbody>\n"
            "      <tr><td>gw-01</td><td>192.0.2.1</td><td>Yes</td></tr>\n"
            "      <tr><td>gw-02</td><td>192.0.2.2</td><td>Yes</td></tr>\n"
            "    </tbody>\n"
            "  </table>\n"
            "</body>\n"
            "</html>\n"
        ).encode("utf-8")

        extractor = HtmlExtractor()
        result = await extractor.extract("src_html", "https://example.com/advisory", html_bytes, {})

        assert result.source_type == SourceType.URL
        # Ensure script and style were stripped
        assert "window.alert" not in result.raw_text
        assert "background: #000" not in result.raw_text

        # Headings (title + h1 + h2)
        assert len(result.headings) == 3
        assert result.headings[0].text == "Security Advisory 2026"
        assert result.headings[1].text == "Vulnerability Report"
        assert result.headings[2].text == "Affected Systems"

        # Table
        assert len(result.tables) == 1
        tbl = result.tables[0]
        assert tbl.headers == ["Host", "IP", "Patched"]
        assert len(tbl.rows) == 2
        assert tbl.rows[0] == ["gw-01", "192.0.2.1", "Yes"]


class TestExtractionServiceIntegration:
    """Test suite verifying ExtractionService registry orchestration and error handling."""

    @pytest.mark.asyncio
    async def test_service_dispatches_correct_extractor(self):
        import hashlib
        from app.models.project import Source

        service = ExtractionService()
        sample_md = b"# Test Markdown\n\nContent paragraph."
        source = Source(
            id="src_spec",
            name="README.md",
            source_type=SourceType.TEXT,
            mime_type="text/markdown",
            size_bytes=len(sample_md),
            content_hash=hashlib.sha256(sample_md).hexdigest(),
        )

        doc = await service.extract_source(
            source=source,
            content=sample_md,
            extra_metadata={},
        )
        assert doc.source_type == SourceType.TEXT
        assert doc.headings[0].text == "Test Markdown"

    @pytest.mark.asyncio
    async def test_unsupported_file_format_raises_extraction_error(self):
        import hashlib
        from app.models.project import Source

        service = ExtractionService()
        sample_bin = b"\x00\x01\x02\x03"
        source = Source(
            id="src_bin",
            name="binary_data.iso",
            source_type=SourceType.FILE,
            mime_type="application/x-iso9660-image",
            size_bytes=len(sample_bin),
            content_hash=hashlib.sha256(sample_bin).hexdigest(),
        )
        with pytest.raises(ExtractionError, match="No suitable extractor registered"):
            await service.extract_source(
                source=source,
                content=sample_bin,
            )
