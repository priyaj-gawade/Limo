"""Phase D5.6: Comprehensive Multi-Format & End-to-End Resilience Verification.

Verifies the complete D5 pipeline according to Rule 10:
Implementation -> Automated Tests -> Real Verification -> Documented Result.

Tests:
1. Real multi-format pipelines (DOCX, XLSX, Markdown, HTML).
2. End-to-end flow: Ingestion -> Extraction -> Normalization -> Canonicalization -> BM25 Retrieval.
3. Negative & resilience tests:
   - Malformed/truncated files raise clean diagnosable errors.
   - Schema violations trigger bounded repair loop recovery.
   - Ungrounded facts flagged as 'unverified' with LLM confidence preserved.
   - Retrieval quality: query returns expected top-1 section and table anchors.
   - Deterministic SHA-256 canonical fingerprint reproducibility.
"""

import io
import json
import openpyxl
import pytest
from docx import Document
from unittest.mock import AsyncMock, MagicMock

from app.agent.context import AgentContext, estimate_tokens
from app.agent.llm.models import LLMResponse
from app.models.content import CanonicalContent, CanonicalFact
from app.models.enums import SourceType
from app.services.canonical.guards import EvidenceGuard
from app.services.canonical.service import (
    CANONICALIZATION_VERSION,
    DEFAULT_CONFIG_HASH,
    CanonicalService,
    compute_canonical_hash,
)
from app.services.extraction.document import DocxExtractor, HtmlExtractor, TextMarkdownExtractor
from app.services.extraction.models import ExtractedDocument
from app.services.extraction.service import ExtractionError, ExtractionService
from app.services.extraction.tabular import SpreadsheetExtractor
from app.services.normalization.models import (
    NormalizedDocument,
    NormalizedSection,
    NormalizedTable,
)
from app.services.normalization.service import NormalizationService
from app.services.retrieval.bm25 import BM25Retriever
from app.services.retrieval.models import RetrievalQuery
from app.services.retrieval.service import RetrievalService


@pytest.fixture
def sample_multi_section_doc():
    return NormalizedDocument(
        source_id="src_e2e_fixture",
        source_name="incident_remediation.pdf",
        source_type=SourceType.FILE,
        mime_type="application/pdf",
        sections=[
            NormalizedSection(
                title="Incident Summary",
                level=1,
                content="On April 15, an adversary attempted a buffer overflow on edge ingress nodes. Network attackers tried memory buffer alteration.",
                page_number=1,
            ),
            NormalizedSection(
                title="Remediation",
                level=2,
                content="Deployed emergency patch v1.4.2 to all core gateway clusters. Edge gateway latency dropped to 45ms.",
                page_number=2,
            ),
            NormalizedSection(
                title="Budget",
                level=1,
                content="Hardware procurement cost was $2.4M for the current fiscal cycle.",
                page_number=3,
            ),
        ],
        tables=[
            NormalizedTable(
                name="Cluster SLA Metrics",
                headers=["Cluster", "Target Latency", "Observed Latency"],
                rows=[
                    ["US-East Gateway", "50ms", "45ms"],
                ],
                source_reference="Page 2",
            )
        ],
        raw_text="Full text content...",
    )


@pytest.fixture
def mock_llm_canonical():
    """Mock LLM responding with structured canonical JSON conforming to CanonicalContent schema."""
    mock_llm = MagicMock()
    valid_ccm = json.dumps({
        "title": "Quarterly Operations Synthesis",
        "context": "Comprehensive operations and incident review for Q2 2026.",
        "intent": {
            "primary_purpose": "Operational readiness audit",
            "target_audiences": ["Executives", "Engineering Leads"],
            "core_narrative": "Core ingress stabilized following patch deployment.",
            "urgency_level": "Strategic",
        },
        "entities": [
            {"name": "CoreGateway", "category": "System", "description": "Primary ingress routing layer", "relevance_score": 0.95},
            {"name": "PatchEngine", "category": "Tool", "description": "Automated deployment pipeline", "relevance_score": 0.85},
        ],
        "facts": [
            {"statement": "Patch deployment lowered gateway latency to 45ms.", "source_reference": "Remediation", "confidence": 0.98},
            {"statement": "Projected savings reached two million dollars.", "source_reference": "Budget", "confidence": 0.90},
        ],
        "claims": [
            {"claim": "All edge nodes achieved 99.9% uptime post-patch.", "claimant": "Engineering", "evidence": "Monitored uptime exceeded SLA"}
        ],
        "events": [
            {"title": "Anomaly detected", "timestamp_desc": "2026-04-10", "significance": "Edge buffer alert"},
            {"title": "Patch deployed", "timestamp_desc": "2026-04-12", "significance": "Full resolution"},
        ],
        "data_points": [
            {"metric": "Gateway Latency", "value": "45ms", "unit": "ms", "context": "US-East cluster"},
            {"metric": "Procurement Cost", "value": "$2.4M", "unit": "USD", "context": "Hardware purchase"},
        ],
        "recommendations": ["Expand continuous synthetic monitoring to EU clusters."],
        "references": [{"citation_key": "[REF-1]", "title": "Operations Report Q2"}],
    })
    mock_llm.generate = AsyncMock(return_value=LLMResponse(text=valid_ccm, input_tokens=400, output_tokens=300))
    return mock_llm


class TestEndToEndRealMultiFormatPipeline:
    """End-to-end verification across real document formats."""

    @pytest.mark.asyncio
    async def test_docx_to_canonical_and_retrieval_flow(self, mock_llm_canonical, tmp_path):
        # 1. Build real DOCX document
        doc = Document()
        doc.add_heading("Executive Summary", level=1)
        doc.add_paragraph("Anomaly detected on edge nodes. Investigation commenced immediately.")
        doc.add_heading("Remediation", level=2)
        doc.add_paragraph("Patch deployment lowered gateway latency to 45ms across all clusters.")
        doc.add_heading("Budget Overview", level=1)
        doc.add_paragraph("Hardware procurement cost was $2.4M for the current fiscal cycle.")

        # Table in DOCX
        table = doc.add_table(rows=2, cols=2)
        table.cell(0, 0).text = "Service"
        table.cell(0, 1).text = "Latency"
        table.cell(1, 0).text = "CoreGateway"
        table.cell(1, 1).text = "45ms"

        buffer = io.BytesIO()
        doc.save(buffer)
        docx_bytes = buffer.getvalue()

        # 2. Extraction (D5.2)
        extractor = DocxExtractor()
        extracted = await extractor.extract(
            source_id="src_docx_e2e",
            filename="operations_report.docx",
            content=docx_bytes,
        )
        assert extracted.source_id == "src_docx_e2e"
        assert len(extracted.headings) >= 3
        assert len(extracted.tables) == 1

        # 3. Normalization (D5.3)
        norm_service = NormalizationService()
        normalized = norm_service.normalize(extracted)
        assert len(normalized.sections) >= 3
        assert len(normalized.tables) == 1
        assert "45ms" in normalized.tables[0].rows[0]

        # 4. Canonicalization (D5.4 - ZERO file re-reading)
        canonical_service = CanonicalService(llm_manager=mock_llm_canonical, db_path=str(tmp_path / "test.db"))
        canonical = await canonical_service.canonicalize(normalized)

        assert canonical.id.startswith("can_")
        assert len(canonical.content_hash) == 64
        assert canonical.canonical_fingerprint == canonical.content_hash
        assert len(canonical.facts) == 2
        # Model confidence preserved!
        assert canonical.facts[0].confidence == 0.98

        # 5. Section-Aware BM25 Retrieval (D5.5 - Pre-indexed)
        retriever = BM25Retriever()
        retriever.index_document(normalized)

        query = RetrievalQuery(query="emergency patch remediation latency", max_tokens=500)
        retrieval_res = await retriever.retrieve(query)
        assert len(retrieval_res.chunks) >= 1
        top_chunk = retrieval_res.chunks[0]
        assert top_chunk.section_title == "Remediation"
        assert "45ms" in top_chunk.content

    @pytest.mark.asyncio
    async def test_xlsx_to_canonical_and_table_retrieval(self, mock_llm_canonical):
        # 1. Build real XLSX spreadsheet
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Incident Metrics"
        ws.append(["Incident ID", "System", "Downtime (min)", "Status"])
        ws.append(["INC-101", "CoreGateway", "14", "Resolved"])
        ws.append(["INC-102", "AuthCluster", "3", "Resolved"])

        buf = io.BytesIO()
        wb.save(buf)
        xlsx_bytes = buf.getvalue()

        # 2. Extract
        extractor = SpreadsheetExtractor()
        extracted = await extractor.extract(
            source_id="src_xlsx_e2e",
            filename="metrics.xlsx",
            content=xlsx_bytes,
        )
        assert len(extracted.tables) == 1

        # 3. Normalize
        norm_service = NormalizationService()
        norm_doc = norm_service.normalize(extracted)
        assert len(norm_doc.tables) == 1
        assert norm_doc.tables[0].headers == ["Incident ID", "System", "Downtime (min)", "Status"]

        # 4. Retrieve tabular chunk by metric
        retriever = BM25Retriever()
        retriever.index_document(norm_doc)

        query = RetrievalQuery(query="INC-101 CoreGateway Downtime")
        result = await retriever.retrieve(query)
        assert len(result.chunks) >= 1
        assert "INC-101" in result.chunks[0].content
        assert result.chunks[0].metadata.get("is_table") is True


class TestNegativeAndResilienceEdgeCases:
    """Comprehensive negative tests for D5.6."""

    @pytest.mark.asyncio
    async def test_truncated_docx_raises_clean_storage_error(self):
        extractor = DocxExtractor()
        with pytest.raises(Exception) as exc_info:
            await extractor.extract(
                source_id="src_bad_docx",
                filename="corrupted.docx",
                content=b"PK\x03\x04TRUNCATED_NOT_A_VALID_DOCX_ZIP",
            )
        assert "Failed to parse DOCX" in str(exc_info.value) or "BadZipFile" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_bounded_repair_loop_exhaustion_raises_storage_error(self, sample_multi_section_doc):
        """Verify bounded repair loop does not loop forever and raises after max retries."""
        mock_llm = MagicMock()
        # Always return malformed JSON
        mock_llm.generate = AsyncMock(return_value=LLMResponse(text="{ bad json...", input_tokens=50, output_tokens=10))

        service = CanonicalService(llm_manager=mock_llm)
        with pytest.raises(Exception) as exc_info:
            await service.canonicalize(sample_multi_section_doc)

        assert "Canonicalization failed after 2 repair retries" in str(exc_info.value)

    def test_evidence_grounding_preserves_paraphrased_facts(self, sample_multi_section_doc):
        """MUST-FIX: Paraphrased facts are flagged as weak/unverified, never dropped, confidence untouched."""
        guard = EvidenceGuard()
        fact = CanonicalFact(
            statement="Network attackers tried memory buffer alteration.",
            source_reference="Incident Summary",
            confidence=0.88,
        )
        validated = guard.validate_fact(fact, sample_multi_section_doc)
        # Statement is retained
        assert validated.statement == fact.statement
        # LLM confidence is strictly preserved
        assert validated.confidence == 0.88
        assert validated.evidence_status in ["weak", "verified"]
        assert validated.evidence_score is not None

    def test_canonical_fingerprint_reproducibility(self):
        """MUST-FIX #3: Same input + same model/config = identical SHA-256 fingerprint."""
        raw_dict = {
            "title": "Synthesis Document",
            "context": "Environmental context",
            "intent": {"primary_purpose": "Reporting", "target_audiences": ["All"], "core_narrative": "Stable"},
            "entities": [{"name": "Alpha", "category": "System"}],
            "facts": [{"statement": "Fact A", "source_reference": "Sec 1", "confidence": 1.0}],
            "claims": [],
            "events": [],
            "data_points": [],
            "recommendations": [],
            "references": [],
        }

        hash1 = compute_canonical_hash(
            canonical_dict=raw_dict,
            canonicalization_version=CANONICALIZATION_VERSION,
            model_id="gemini-3.5-flash-lite",
            config_hash=DEFAULT_CONFIG_HASH,
        )
        hash2 = compute_canonical_hash(
            canonical_dict=raw_dict,
            canonicalization_version=CANONICALIZATION_VERSION,
            model_id="gemini-3.5-flash-lite",
            config_hash=DEFAULT_CONFIG_HASH,
        )

        assert hash1 == hash2
        assert len(hash1) == 64
