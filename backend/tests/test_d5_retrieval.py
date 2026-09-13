"""Unit and integration tests for Phase D5.5: Context Retrieval & Token Budget Slicing.

Tests all 5 MUST-FIX items:
1. SourceReadTool explicit action='retrieve_context' while preserving direct get_source_content.
2. BM25 builds and indexes normalized chunks once, reusing index for multiple queries.
3. Configurable token budget at agent context and query level.
4. Token estimation is strictly consistent with D4.2 estimate_tokens().
5. High-precision retrieval quality: expected section top-ranked, anchors preserved, table chunking.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.agent.context import AgentContext, estimate_tokens
from app.agent.tools.source_tool import SourceReadTool
from app.main import app
from app.models.enums import SourceType
from app.models.project import Source
from app.services.normalization.models import (
    NormalizedDocument,
    NormalizedSection,
    NormalizedTable,
)
from app.services.retrieval.bm25 import BM25Retriever, DocumentIndex
from app.services.retrieval.models import RetrievalQuery
from app.services.retrieval.service import RetrievalService


@pytest.fixture
def sample_multi_section_doc():
    return NormalizedDocument(
        source_id="src_retrieval_01",
        source_name="incident_remediation.pdf",
        source_type=SourceType.FILE,
        mime_type="application/pdf",
        sections=[
            NormalizedSection(
                title="Incident Summary",
                level=1,
                content="On April 15, an adversary attempted a buffer overflow on edge ingress nodes. No data exfiltration occurred.",
                page_number=1,
            ),
            NormalizedSection(
                title="Technical Remediation",
                level=2,
                content="Deployed emergency patch v1.4.2 to all core gateway clusters. Edge gateway latency dropped to 45ms and memory buffer usage stabilized.",
                page_number=2,
            ),
            NormalizedSection(
                title="Quarterly Budget Outlook",
                level=1,
                content="Travel expenses and conference attendance were paused for Q2. Hardware procurement remains on schedule with minimal cost variance.",
                page_number=3,
            ),
        ],
        tables=[
            NormalizedTable(
                name="Cluster SLA Metrics",
                headers=["Cluster", "Target Latency", "Observed Latency"],
                rows=[
                    ["US-East Gateway", "50ms", "45ms"],
                    ["EU-Central Gateway", "50ms", "48ms"],
                ],
                source_reference="Page 2",
            )
        ],
        raw_text="Full text content...",
    )


class TestBM25IndexingAndQuality:
    """Test suite for MUST-FIX #2 (build once, query many) and MUST-FIX #5 (retrieval quality)."""

    def test_build_index_once_and_reuse_for_multiple_queries(self, sample_multi_section_doc):
        retriever = BM25Retriever()

        # Pre-index document once
        retriever.index_document(sample_multi_section_doc)
        assert retriever.has_index("src_retrieval_01")
        doc_index = retriever._indices["src_retrieval_01"]

        # 4 chunks: 3 sections + 1 table
        assert len(doc_index.chunks) == 4
        assert len(doc_index.tokenized_chunks) == 4

        # Query 1: Query about patch remediation
        scores_1 = doc_index.score_query("emergency patch gateway latency")
        assert len(scores_1) > 0
        top_chunk_idx, top_score = scores_1[0]
        top_chunk = doc_index.chunks[top_chunk_idx]
        assert top_chunk.section_title == "Technical Remediation"
        assert top_chunk.page_number == 2

        # Query 2: Query about financial budget without re-indexing
        scores_2 = doc_index.score_query("travel expenses hardware procurement")
        assert len(scores_2) > 0
        top_chunk_idx_2, top_score_2 = scores_2[0]
        top_chunk_2 = doc_index.chunks[top_chunk_idx_2]
        assert top_chunk_2.section_title == "Quarterly Budget Outlook"
        assert top_chunk_2.page_number == 3

    @pytest.mark.asyncio
    async def test_retrieval_quality_table_query_and_anchor_preservation(self, sample_multi_section_doc):
        """MUST-FIX #5: Table query correctly matches table chunk with intact metadata."""
        retriever = BM25Retriever()
        retriever.index_document(sample_multi_section_doc)

        query = RetrievalQuery(query="Cluster SLA Metrics EU-Central Gateway", source_ids=["src_retrieval_01"])
        result = await retriever.retrieve(query)

        assert len(result.chunks) > 0
        top_chunk = result.chunks[0]
        assert "Cluster SLA Metrics" in top_chunk.section_title
        assert "EU-Central Gateway" in top_chunk.content
        assert top_chunk.metadata.get("is_table") is True


class TestTokenBudgetSlicing:
    """Test suite for MUST-FIX #3 (dynamic budget) and MUST-FIX #4 (consistent token estimation)."""

    @pytest.mark.asyncio
    async def test_strict_token_budget_enforcement(self, sample_multi_section_doc):
        retriever = BM25Retriever()
        retriever.index_document(sample_multi_section_doc)

        # Budget of 40 tokens (roughly 160 chars) - only 1 chunk should fit
        query = RetrievalQuery(query="gateway patch latency budget", max_tokens=40)
        result = await retriever.retrieve(query, max_tokens=40)

        # Total tokens must not exceed budget
        assert result.total_tokens_returned <= 40
        assert len(result.chunks) >= 1
        assert result.budget_exhausted is True

        # Verify token counts match shared D4.2 estimate_tokens() exactly
        for chunk in result.chunks:
            assert chunk.estimated_tokens == estimate_tokens(chunk.content)

    @pytest.mark.asyncio
    async def test_generous_budget_returns_all_matching_chunks(self, sample_multi_section_doc):
        retriever = BM25Retriever()
        retriever.index_document(sample_multi_section_doc)

        query = RetrievalQuery(query="gateway latency buffer", max_tokens=2000)
        result = await retriever.retrieve(query, max_tokens=2000)

        # All chunks with relevant terms returned
        assert len(result.chunks) >= 2
        assert result.budget_exhausted is False


class TestSourceReadToolExplicitAction:
    """Test suite for MUST-FIX #1: Explicit retrieve_context action."""

    @pytest.mark.asyncio
    async def test_source_read_tool_retrieve_context_action(self, sample_multi_section_doc):
        mock_retrieval_svc = MagicMock()
        mock_result = MagicMock()
        mock_chunk = MagicMock()
        mock_chunk.model_dump.return_value = {
            "chunk_id": "c1",
            "section_title": "Technical Remediation",
            "content": "Emergency patch v1.4.2 applied.",
            "relevance_score": 2.45,
            "estimated_tokens": 15,
        }
        mock_result.query = "emergency patch"
        mock_result.chunks = [mock_chunk]
        mock_result.total_tokens_returned = 15
        mock_result.budget_exhausted = False

        mock_retrieval_svc.retrieve_context = AsyncMock(return_value=mock_result)

        tool = SourceReadTool(retrieval=mock_retrieval_svc)
        ctx = AgentContext(session_id="sess_retrieve", retrieval_budget_tokens=1500)

        # 1. Successful retrieve_context
        res = await tool.execute({
            "action": "retrieve_context",
            "source_id": "src_retrieval_01",
            "query": "emergency patch",
        }, context=ctx)

        assert res.success is True
        assert res.output["chunks_count"] == 1
        assert res.output["total_tokens"] == 15
        mock_retrieval_svc.retrieve_context.assert_awaited_once()

        # 2. retrieve_context missing query fails gracefully
        res_fail = await tool.execute({
            "action": "retrieve_context",
            "source_id": "src_retrieval_01",
        }, context=ctx)
        assert res_fail.success is False
        assert "Missing required 'query'" in res_fail.error

    @pytest.mark.asyncio
    async def test_get_source_content_remains_direct_read(self):
        mock_source_svc = MagicMock()
        mock_source_svc.get_source.return_value = Source(
            id="src_direct_01",
            name="notes.txt",
            source_type=SourceType.TEXT,
            mime_type="text/plain",
            size_bytes=30,
            content_hash="a" * 64,
        )
        mock_source_svc.read_source_content.return_value = b"Direct content from file."

        tool = SourceReadTool(service=mock_source_svc)
        res = await tool.execute({
            "action": "get_source_content",
            "source_id": "src_direct_01",
            "max_chars": 100,
        })

        assert res.success is True
        assert res.output["content"] == "Direct content from file."
        assert res.output["truncated"] is False


class TestRetrievalApiEndpoint:
    """Test suite for POST /api/v1/sources/{source_id}/retrieve."""

    def test_retrieve_endpoint(self, sample_multi_section_doc):
        client = TestClient(app)

        with patch("app.services.source_service.source_service.get_source") as mock_get_source, \
             patch("app.services.retrieval.service.retrieval_service.retrieve_context") as mock_retrieve:
            mock_get_source.return_value = Source(
                id="src_retrieval_01",
                name="incident_remediation.pdf",
                source_type=SourceType.FILE,
                mime_type="application/pdf",
                size_bytes=1000,
                content_hash="b" * 64,
            )

            from app.services.retrieval.models import RetrievalResult, RetrievedChunk
            mock_retrieve.return_value = RetrievalResult(
                query="emergency patch",
                chunks=[
                    RetrievedChunk(
                        chunk_id="c1",
                        source_id="src_retrieval_01",
                        chunk_index=0,
                        section_title="Technical Remediation",
                        content="Deployed emergency patch v1.4.2.",
                        relevance_score=1.8,
                        estimated_tokens=12,
                    )
                ],
                total_chunks_found=1,
                total_tokens_returned=12,
                budget_exhausted=False,
            )

            res = client.post(
                "/api/v1/sources/src_retrieval_01/retrieve",
                json={"query": "emergency patch", "max_tokens": 500},
            )

            assert res.status_code == 200
            data = res.json()
            assert data["query"] == "emergency patch"
            assert len(data["chunks"]) == 1
            assert data["chunks"][0]["section_title"] == "Technical Remediation"
